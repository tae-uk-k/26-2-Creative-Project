"""실제 서비스 변경 없이 아카이브 경계·스키마 검사·실패 롤백을 확인한다."""

import importlib.util
import io
import os
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "infra/scripts/deploy.py"
spec = importlib.util.spec_from_file_location("seelo_deploy", SCRIPT)
deployment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)
TAG = "git-" + "a" * 40


def test_only_image_tag_changes_in_protected_environment():
    original = b"SECRET_KEY='keep-unchanged'\nSEELO_IMAGE_TAG='old'\nSMTP_PASSWORD='preserved'\n"
    changed = deployment.image_environment(original, TAG)
    assert changed == original.replace(b"SEELO_IMAGE_TAG='old'", b"SEELO_IMAGE_TAG=" + TAG.encode())
    for content, tag in [(b"OTHER=1\n", TAG), (original, "x; bad"), (original * 2, TAG)]:
        with pytest.raises(ValueError):
            deployment.image_environment(content, tag)


@pytest.mark.parametrize(
    "name,link",
    [
        ("../outside", False),
        ("/absolute", False),
        ("backend/.env", False),
        ("backend/.env.production", False),
        ("backend/private.key", False),
        ("gha-creds-test.json", False),
        ("link", True),
    ],
)
def test_unsafe_archive_is_rejected_before_extract(tmp_path, name, link):
    bundle = tmp_path / "bundle.tar.gz"
    with tarfile.open(bundle, "w:gz") as tar:
        good = tarfile.TarInfo("good.txt")
        good.size = 2
        tar.addfile(good, io.BytesIO(b"ok"))
        item = tarfile.TarInfo(name)
        if link:
            item.type = tarfile.SYMTYPE
            item.linkname = "/etc/passwd"
        tar.addfile(item)
    target = tmp_path / "release"
    target.mkdir()
    with pytest.raises(ValueError, match="unsafe_archive_member"):
        deployment.extract_archive(bundle, target)
    assert not list(target.iterdir())


def test_migration_heads_reads_ast_without_executing_code(tmp_path):
    (tmp_path / "a.py").write_text("revision='a'\ndown_revision=None\nraise Exception('must not execute')\n")
    (tmp_path / "b.py").write_text("revision: str='b'\ndown_revision='a'\n")
    assert deployment.migration_heads(tmp_path) == ["b"]
    (tmp_path / "c.py").write_text("revision='c'\ndown_revision='missing'\n")
    with pytest.raises(ValueError, match="invalid_migration_graph"):
        deployment.migration_heads(tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="실제 운영 Linux symlink 동작은 CI에서 검증")
@pytest.mark.parametrize("fail", [False, True])
def test_activation_rolls_back_env_and_current_together(tmp_path, fail):
    releases = tmp_path / "releases"
    releases.mkdir()
    previous = releases / "old"
    previous.mkdir()
    candidate = releases / "new"
    candidate.mkdir()
    current = tmp_path / "current"
    current.symlink_to(previous)
    environment = tmp_path / "production.env"
    original = b"SECRET_KEY=keep\nSEELO_IMAGE_TAG=previous\n"
    environment.write_bytes(original)
    calls = []

    def runner(argv):
        calls.append(argv)

    def verify():
        assert current.resolve() == candidate
        assert TAG.encode() in environment.read_bytes()
        if fail:
            raise RuntimeError("health_failed")

    if fail:
        with pytest.raises(RuntimeError, match="health_failed"):
            deployment.activate(candidate, current, environment, TAG, runner, verify)
        assert current.resolve() == previous and environment.read_bytes() == original
        assert len(calls) == 2 and str(previous / "docker-compose.prod.yml") in calls[-1]
    else:
        deployment.activate(candidate, current, environment, TAG, runner, verify)
        assert current.resolve() == candidate and len(calls) == 1
    backups = list(tmp_path.glob("production.env.before-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == original
    assert candidate.exists() and previous.exists()


def test_browser_worker_is_opt_in_by_exact_setting():
    assert deployment.browser_worker_enabled(b"A=1\nSEELO_BROWSER_WORKER=true\n")
    assert deployment.browser_worker_enabled(b"SEELO_BROWSER_WORKER=true\r\n")
    assert not deployment.browser_worker_enabled(b"SEELO_BROWSER_WORKER=false\n")
    assert not deployment.browser_worker_enabled(b"# SEELO_BROWSER_WORKER=true\n")
    assert not deployment.browser_worker_enabled(b"SEELO_BROWSER_WORKER=truex\n")


def test_web_build_args_pass_only_public_manager_values():
    env = "SECRET_KEY=s\nVITE_SEELO_MANAGER_NAME=seelo 담당\r\nVITE_SEELO_MANAGER_PHONE=010-1234-5678\n"
    assert deployment.web_build_args(env.encode()) == [
        "--build-arg",
        "VITE_SEELO_MANAGER_NAME=seelo 담당",
        "--build-arg",
        "VITE_SEELO_MANAGER_PHONE=010-1234-5678",
    ]
    # 비어 있거나 주석이면 넘기지 않는다. 화면은 복사 버튼을 숨긴다.
    assert deployment.web_build_args(b"VITE_SEELO_MANAGER_NAME=\n# VITE_SEELO_MANAGER_PHONE=1\n") == []
    with pytest.raises(ValueError):
        deployment.web_build_args(b"VITE_SEELO_MANAGER_NAME=" + b"x" * 101 + b"\n")


@pytest.mark.skipif(os.name == "nt", reason="실제 운영 Linux symlink 동작은 CI에서 검증")
def test_failed_activation_stops_browser_worker_of_new_release(tmp_path):
    releases = tmp_path / "releases"
    releases.mkdir()
    previous, candidate = releases / "old", releases / "new"
    previous.mkdir()
    candidate.mkdir()
    current = tmp_path / "current"
    current.symlink_to(previous)
    environment = tmp_path / "production.env"
    environment.write_bytes(b"SEELO_IMAGE_TAG=previous\n")
    calls = []

    def verify():
        raise RuntimeError("health_failed")

    services = [*deployment.SERVICES, deployment.BROWSER_WORKER]
    with pytest.raises(RuntimeError):
        deployment.activate(candidate, current, environment, TAG, calls.append, verify, services)
    assert deployment.BROWSER_WORKER in calls[0]
    assert deployment.BROWSER_WORKER not in calls[1]
    assert calls[2][-2:] == ["stop", deployment.BROWSER_WORKER]
