"""사용자 로그인 세션의 브리지·SSH 감독. PC 전원/세션 설정은 변경하지 않는다."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

REMOTE_SOCKET = "/home/ubuntu/seelo-ai/bridge.sock"
PREPARE_SOCKET = r"""
from pathlib import Path
import os,socket,stat,time
root=Path('/home/ubuntu/seelo-ai')
if root.is_symlink() or root.resolve()!=root:raise SystemExit(1)
root.mkdir(mode=0o700,exist_ok=True)
p=root/'bridge.sock'
if p.exists():
 if not stat.S_ISSOCK(p.lstat().st_mode) or p.stat().st_uid!=os.getuid():raise SystemExit(2)
 try:
  with socket.socket(socket.AF_UNIX) as s:
   s.settimeout(3);s.connect(str(p))
   s.sendall(b'GET /health HTTP/1.0\r\nHost: seelo-ai.local\r\n\r\n')
   if s.recv(256).split(b' ',2)[1:2]==[b'401']:
    print('ACTIVE');raise SystemExit(0)
 except OSError:pass
 history=root/'quarantine';history.mkdir(mode=0o700,exist_ok=True)
 p.rename(history/(str(time.time_ns())+'.sock'))
print('READY')
"""


def bridge_health(token: str) -> bool:
    try:
        response = httpx.get(
            "http://127.0.0.1:18765/health",
            timeout=3,
            trust_env=False,
            headers={"Authorization": "Bearer " + token},
        )
        return response.status_code == 200 and response.json().get("mode") == "local_cli"
    except (httpx.HTTPError, ValueError):
        return False


def ssh_args(folder: Path) -> list[str]:
    return [
        str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/OpenSSH/ssh.exe"),
        "-i",
        str(folder / "oci-seelo-prod.key"),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "UserKnownHostsFile=" + str(folder / "gcp-known-hosts"),
        "-o",
        "KexAlgorithms=curve25519-sha256",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    args = parser.parse_args()
    env_file = Path(args.env_file).resolve()
    load_dotenv(env_file, override=False)
    directory = Path(os.environ["LOCAL_AI_DATA_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    lock = (directory / "supervisor.lock").open("a+b")
    lock.seek(0)
    if os.name == "nt":
        import msvcrt

        try:
            if lock.read(1) == b"":
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return
    token = os.environ["LOCAL_AI_TOKEN"]
    backend = Path(__file__).resolve().parents[2]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    out = (directory / "supervisor.log").open("a", encoding="utf-8")
    ssh = ssh_args(env_file.parent)
    bridge = tunnel = None
    try:
        while True:
            healthy = bridge_health(token)
            if not healthy and (bridge is None or bridge.poll() is not None):
                bridge = subprocess.Popen(
                    [sys.executable, "-m", "seelo.local_ai.server", "--env-file", str(env_file)],
                    cwd=backend,
                    creationflags=flags,
                    stdout=out,
                    stderr=out,
                )
            remote = "waiting_for_local_bridge"
            if healthy:
                try:
                    check = subprocess.run(
                        [*ssh, "ubuntu@34.64.188.249", "python3 -"],
                        input=PREPARE_SOCKET,
                        text=True,
                        capture_output=True,
                        timeout=20,
                        creationflags=flags,
                    )
                    remote = check.stdout.strip() if check.returncode == 0 else "ssh_unavailable"
                    if remote == "READY" and (tunnel is None or tunnel.poll() is not None):
                        tunnel = subprocess.Popen(
                            [
                                *ssh,
                                "-N",
                                "-T",
                                "-o",
                                "ExitOnForwardFailure=yes",
                                "-R",
                                REMOTE_SOCKET + ":127.0.0.1:18765",
                                "ubuntu@34.64.188.249",
                            ],
                            creationflags=flags,
                            stdout=out,
                            stderr=out,
                        )
                        remote = "connecting"
                except (OSError, subprocess.TimeoutExpired):
                    remote = "ssh_unavailable"
            status = {
                "local_bridge": healthy,
                "ssh_socket": remote,
                "updated_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
            }
            (directory / "supervisor-status.json").write_text(json.dumps(status), encoding="utf-8")
            time.sleep(30)
    finally:
        for process in (tunnel, bridge):
            if process is not None and process.poll() is None:
                process.terminate()
        out.close()
        lock.close()


if __name__ == "__main__":
    main()
