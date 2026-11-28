"""검증된 VM 백업을 SSH 사용자 전용 export에 복사한다. 기존 파일을 덮어쓰거나 삭제하지 않는다."""

import hashlib
import json
import os
import pwd
import re
import stat
from pathlib import Path

SOURCE = Path("/var/backups/seelo")
EXPORT = Path("/home/ubuntu/seelo-backups-export")
NAME = re.compile(r"seelo_\d{8}T\d{6}Z\.dump\Z")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    owner = pwd.getpwnam("ubuntu")
    if EXPORT.is_symlink():
        raise SystemExit("unsafe export directory")
    EXPORT.mkdir(mode=0o700, exist_ok=True)
    os.chown(EXPORT, owner.pw_uid, owner.pw_gid)
    os.chmod(EXPORT, 0o700)
    result = []
    for source in sorted(SOURCE.iterdir()):
        if not NAME.fullmatch(source.name) or not stat.S_ISREG(source.lstat().st_mode):
            continue
        target = EXPORT / source.name
        expected = digest(source)
        if not target.exists():
            with target.open("xb") as output, source.open("rb") as stream:
                os.fchmod(output.fileno(), 0o600)
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
                os.fchown(output.fileno(), owner.pw_uid, owner.pw_gid)
        if target.is_symlink() or digest(target) != expected:
            raise SystemExit("existing backup differs; preserved for review")
        result.append({"name": source.name, "bytes": source.stat().st_size, "sha256": expected})
    print(json.dumps({"backups": result}))


if __name__ == "__main__":
    main()
