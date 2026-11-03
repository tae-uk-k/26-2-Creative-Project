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
