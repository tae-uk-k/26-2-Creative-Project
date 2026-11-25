"""GitHub Actions 배포. DB 스키마는 변경하지 않고 실패 시 이전 릴리스로 복구한다."""

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import tarfile
import time
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

SERVICES = ["api", "worker-main", "worker-ai-openai", "worker-ai-gemini", "web"]
# 쇼핑몰 브라우저 작업(commerce_browser 큐)은 Playwright 이미지의 worker-fix가 실행한다.
# 운영 env에 SEELO_BROWSER_WORKER=true를 명시한 경우에만 이미지를 빌드하고 함께 올린다.
BROWSER_WORKER = "worker-fix"


def browser_worker_enabled(content: bytes) -> bool:
    return re.search(rb"(?m)^SEELO_BROWSER_WORKER=true\r?$", content) is not None
HOST = "https://seelo.site"


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def extract_archive(bundle: Path, destination: Path) -> None:
    with tarfile.open(bundle, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) > 20000 or sum(item.size for item in members) > 512 * 1024 * 1024:
            raise ValueError("archive_too_large")
        for item in members:
            path = PurePosixPath(item.name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in item.name
                or not (item.isfile() or item.isdir())
                or (path.name.startswith(".env") and path.name != ".env.example")
                or path.suffix in {".key", ".pem", ".dump"}
                or path.name.startswith("gha-creds-")
            ):
                raise ValueError("unsafe_archive_member")
        archive.extractall(destination, filter="data")


def migration_heads(folder: Path) -> list[str]:
    revisions, parents = set(), set()
    for file in folder.glob("*.py"):
        values = {}
        for node in ast.parse(file.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
                    values[target.id] = ast.literal_eval(node.value)
        if "revision" not in values:
            continue
        revision = values["revision"]
        if not isinstance(revision, str) or revision in revisions:
            raise ValueError("invalid_migration_revision")
        revisions.add(revision)
        parent = values.get("down_revision")
        parents.update(parent if isinstance(parent, (tuple, list)) else [parent] if parent else [])
    if not revisions or not parents.issubset(revisions):
        raise ValueError("invalid_migration_graph")
    return sorted(revisions - parents)


def image_environment(content: bytes, tag: str) -> bytes:
    if not re.fullmatch(r"git-[a-f0-9]{40}", tag):
        raise ValueError("invalid_image_tag")
    value, count = re.subn(rb"(?m)^SEELO_IMAGE_TAG=[^\r\n]*", b"SEELO_IMAGE_TAG=" + tag.encode(), content)
    if count != 1:
        raise ValueError("image_setting_not_unique")
    return value


def atomic_write(path: Path, content: bytes) -> None:
    pending = path.with_name(path.name + ".pending." + uuid.uuid4().hex)
    with pending.open("xb") as stream:
        os.chmod(pending, 0o600)
        stream.write(content)
    os.replace(pending, path)


def point_current(current: Path, release: Path) -> None:
    pending = current.with_name("current.pending." + uuid.uuid4().hex)
    pending.symlink_to(release, target_is_directory=True)
    os.replace(pending, current)


def compose(release: Path, environment: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        "seelo-prod",
        "--env-file",
        str(environment),
        "-f",
        str(release / "docker-compose.prod.yml"),
        "-f",
        str(release / "docker-compose.local-ai.yml"),
    ]


def activate(
    candidate: Path, current: Path, environment: Path, tag: str, runner, verify, services=None
) -> None:
    services = list(services or SERVICES)
    if not current.is_symlink() or environment.is_symlink():
        raise ValueError("unexpected_deployment_layout")
    previous = current.resolve(strict=True)
    if candidate.parent != previous.parent:
        raise ValueError("release_outside_expected_root")
    original = environment.read_bytes()
    replacement = image_environment(original, tag)
    backup = environment.with_name(environment.name + ".before-" + tag + "." + uuid.uuid4().hex)
    with backup.open("xb") as stream:
        os.chmod(backup, 0o600)
        stream.write(original)
    try:
        atomic_write(environment, replacement)
        point_current(current, candidate)
        runner(
            compose(candidate, environment)
            + ["up", "-d", "--no-deps", "--wait", "--wait-timeout", "180", *services]
        )
        verify()
    except Exception:
        # 실패한 후보·로그·이미지는 보존하고, env와 current를 함께 원복한다.
        atomic_write(environment, original)
        point_current(current, previous)
        runner(
            compose(previous, environment)
            + ["up", "-d", "--no-deps", "--wait", "--wait-timeout", "180", *SERVICES]
        )
        if BROWSER_WORKER in services:
            # 이전 릴리스에 브라우저 워커 이미지가 없을 수 있다. 작업은 큐에 남기고 워커만 멈춘다.
            runner(compose(previous, environment) + ["stop", BROWSER_WORKER])
        raise


def public_ready(commit: str) -> None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(12):
        try:
            with opener.open(HOST + "/api/health", timeout=10) as response:
                health = json.load(response)
            with opener.open(HOST + "/deployment.json", timeout=10) as response:
                deployed = json.load(response)
            if health == {"status": "ok", "db": "ok"} and deployed.get("commit") == commit:
                return
        except (OSError, ValueError):
            pass
        if attempt < 11:
            time.sleep(5)
    raise RuntimeError("public_readiness_failed")


def main() -> None:
    import fcntl

    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    if os.geteuid() != 0 or not re.fullmatch(r"[a-f0-9]{40}", args.commit):
        raise SystemExit("root_and_valid_commit_required")
    if not re.fullmatch(r"[a-f0-9]{64}", args.sha256) or digest(args.bundle) != args.sha256:
        raise SystemExit("bundle_hash_mismatch")
    lock = Path("/run/seelo-deploy.lock").open("a+b")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    root, current, environment = (
        Path("/opt/seelo"),
        Path("/opt/seelo/current"),
        Path("/etc/seelo/production.env"),
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    release = root / "releases" / ("git-" + args.commit + "-" + stamp)
    release.mkdir(mode=0o755, parents=False, exist_ok=False)
    logs = Path("/var/log/seelo-deploy")
    logs.mkdir(mode=0o700, exist_ok=True)
    log_path = logs / (args.commit + "-" + stamp + ".log")
    log = log_path.open("x", encoding="utf-8")
    os.chmod(log_path, 0o600)
    stage = "extract"

    def run(command: list[str], **kwargs) -> str:
        result = subprocess.run(command, text=True, capture_output=True, check=False, timeout=1200, **kwargs)
        log.write(result.stdout + result.stderr)
        log.flush()
        if result.returncode:
            raise RuntimeError("command_failed")
        return result.stdout

    try:
        extract_archive(args.bundle, release)
        expected = migration_heads(release / "backend/migrations/versions")
        stage = "schema_check"
        actual = run(
            compose(current.resolve(), environment)
            + [
                "exec",
                "-T",
                "db",
                "psql",
                "-U",
                "seelo",
                "-d",
                "seelo",
                "-tAc",
                "SELECT version_num FROM alembic_version ORDER BY version_num",
            ]
        )
        if actual.split() != expected:
            raise RuntimeError("migration_requires_manual_approval")
        stage = "backup"
        run(
            ["flock", "--nonblock", "/run/seelo-backup.lock", "sh", str(current / "infra/scripts/backup.sh")],
            env={**os.environ, "SEELO_ENV_FILE": str(environment), "BACKUP_DIR": "/var/backups/seelo"},
        )
        stage = "build"
        tag = "git-" + args.commit
        run(
            [
                "docker",
                "build",
                "--label",
                "org.opencontainers.image.revision=" + args.commit,
                "-t",
                "seelo-backend:" + tag,
                str(release / "backend"),
            ]
        )
        # 화면은 프런트 빌드 결과를 담은 nginx 이미지로 제공한다. 타입·빌드 오류면 배포하지 않는다.
        run(
            [
                "docker",
                "build",
                "--label",
                "org.opencontainers.image.revision=" + args.commit,
                "-t",
                "seelo-web:" + tag,
                str(release / "frontend"),
            ]
        )
        services = list(SERVICES)
        if browser_worker_enabled(environment.read_bytes()):
            run(
                [
                    "docker",
                    "build",
                    "--label",
                    "org.opencontainers.image.revision=" + args.commit,
                    "-f",
                    str(release / "backend/Dockerfile.fix"),
                    "-t",
                    "seelo-backend-fix:" + tag,
                    str(release / "backend"),
                ]
            )
            services.append(BROWSER_WORKER)
        meta = release / "infra/nginx/meta"
        meta.mkdir(parents=True, exist_ok=True)
        (meta / "deployment.json").write_text(
            json.dumps({"commit": args.commit, "deployed_at_utc": stamp}) + "\n", encoding="utf-8"
        )
        stage = "activate"
        activate(release, current, environment, tag, run, lambda: public_ready(args.commit), services)
        print(json.dumps({"status": "deployed", "commit": args.commit, "schema_migration": False}))
    except Exception as error:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "stage": stage,
                    "error_type": type(error).__name__,
                    "reason": str(error)
                    if isinstance(error, (RuntimeError, ValueError))
                    else "see_protected_log",
                }
            )
        )
        raise SystemExit(1) from None
    finally:
        log.close()
        lock.close()


if __name__ == "__main__":
    main()
