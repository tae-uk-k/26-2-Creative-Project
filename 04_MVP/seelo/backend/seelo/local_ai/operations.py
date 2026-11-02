"""PC 기준 5분 HTTPS 확인·시간당 외부 백업. 실제 이메일 알림은 명시적 설정 전에는 보내지 않는다."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import dotenv_values

from seelo.local_ai.supervisor import ssh_args

BACKUP_NAME = re.compile(r"seelo_\d{8}T\d{6}Z\.dump\Z")


def check_health() -> dict:
    try:
        response = httpx.get(
            "https://seelo.site/api/health", timeout=10, follow_redirects=False, trust_env=False
        )
        ok = response.status_code == 200 and response.json() == {"status": "ok", "db": "ok"}
        return {"ok": ok, "reason": "ok" if ok else "http_or_database"}
    except (httpx.HTTPError, ValueError):
        return {"ok": False, "reason": "external_connection_failed"}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sync_backups(secret_dir: Path) -> list[dict]:
    command = [
        *ssh_args(secret_dir),
        "ubuntu@34.64.188.249",
        "sudo python3 /usr/local/lib/seelo/export-backups.py",
    ]
    response = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if response.returncode:
        raise RuntimeError("backup_export_unavailable")
    payload = json.loads(response.stdout)
    backups = payload.get("backups") if isinstance(payload, dict) else None
    if not isinstance(backups, list) or len(backups) > 256 or any(
        not isinstance(entry, dict)
        or not isinstance(entry.get("name"), str)
        or not isinstance(entry.get("sha256"), str)
        for entry in backups
    ):
        raise ValueError("invalid_backup_manifest")
    folder = secret_dir / "backups"
    folder.mkdir(exist_ok=True)
    verified = []
    for entry in backups:
        name, expected = entry["name"], entry["sha256"]
        if not BACKUP_NAME.fullmatch(name) or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("invalid_backup_manifest")
        target = folder / name
        if target.is_symlink():
            raise ValueError("unsafe_backup_target")
        if not target.exists():
            pending = folder / (name + ".partial." + str(time.time_ns()))
            ssh = ssh_args(secret_dir)
            scp = str(Path(ssh[0]).with_name("scp.exe"))
            result = subprocess.run(
                [
                    scp,
                    *ssh[1:],
                    "ubuntu@34.64.188.249:/home/ubuntu/seelo-backups-export/" + name,
                    str(pending),
                ],
                capture_output=True,
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if result.returncode:
                raise RuntimeError("backup_download_failed")
            if file_hash(pending) != expected:
                quarantine = folder / "quarantine"
                quarantine.mkdir(exist_ok=True)
                pending.rename(quarantine / pending.name)
                raise ValueError("backup_hash_mismatch")
            pending.rename(target)
        if file_hash(target) != expected:
            raise ValueError("existing_backup_hash_mismatch")
        verified.append({"name": name, "sha256": expected})
    return verified


def run_once(env_file: Path, *, force_backup: bool = False) -> dict:
    settings = dotenv_values(env_file)
    directory = Path(settings["LOCAL_AI_DATA_DIR"])
    state_path = directory / "operations-status.json"
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    now = datetime.now(timezone(timedelta(hours=9))).isoformat()
    health = check_health()
    if previous.get("health") != health:
        with (directory / "health-events.jsonl").open("a", encoding="utf-8") as events:
            events.write(json.dumps({"time_kst": now, "health": health}) + "\n")
    result = {**previous, "checked_at_kst": now, "health": health, "notifications_enabled": False}
    if force_backup or time.time() - previous.get("last_backup_check_epoch", 0) >= 3600:
        try:
            verified = sync_backups(env_file.parent)
            result.update(backups_verified=verified, backup_error=None, last_backup_check_epoch=time.time())
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as error:
            result["backup_error"] = type(error).__name__
    pending = directory / "operations-status.next.json"
    pending.write_text(json.dumps(result, indent=2), encoding="utf-8")
    pending.replace(state_path)
    return {
        "health_ok": health["ok"],
        "backups_verified": len(result.get("backups_verified", [])),
        "backup_error": result.get("backup_error"),
        "notifications_enabled": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--force-backup", action="store_true")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    env_file = Path(args.env_file).resolve()
    directory = Path(dotenv_values(env_file)["LOCAL_AI_DATA_DIR"])
    lock = (directory / "operations.lock").open("a+b")
    if os.name == "nt":
        import msvcrt

        try:
            lock.seek(0)
            if not lock.read(1):
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
    try:
        while True:
            try:
                print(json.dumps(run_once(env_file, force_backup=args.force_backup)), flush=True)
            except (OSError, ValueError, KeyError) as error:
                print(json.dumps({"operations_error": type(error).__name__}), flush=True)
            if not args.watch:
                break
            time.sleep(300)
    finally:
        lock.close()


if __name__ == "__main__":
    main()
