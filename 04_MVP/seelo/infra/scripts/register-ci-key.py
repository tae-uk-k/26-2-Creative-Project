"""현재 CI 실행의 SSH 공개키를 VM 한 대에 30분 유효기간으로 추가한다."""

import argparse
import json
import subprocess
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path


def metadata_with_key(metadata: dict, public_key: str, expires: str) -> dict:
    parts = public_key.split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError("expected_ed25519_public_key")
    entry = (
        "ubuntu:"
        + " ".join(parts[:2])
        + " google-ssh "
        + json.dumps({"userName": "ubuntu", "expireOn": expires}, separators=(",", ":"))
    )
    items = [dict(item) for item in metadata.get("items", [])]
    for item in items:
        if item["key"] == "ssh-keys":
            item["value"] = item["value"].rstrip() + "\n" + entry
            break
    else:
        items.append({"key": "ssh-keys", "value": entry})
    return {"fingerprint": metadata.get("fingerprint"), "items": items}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--zone", required=True)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    args = parser.parse_args()
    token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
    endpoint = (
        "https://compute.googleapis.com/compute/v1/projects/"
        + args.project
        + "/zones/"
        + args.zone
        + "/instances/"
        + args.instance
    )

    def request(url, data=None):
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)

    vm = request(endpoint)
    expires = (datetime.now(UTC) + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    metadata = metadata_with_key(vm.get("metadata", {}), args.public_key.read_text(), expires)
    operation = request(endpoint + "/setMetadata", metadata)
    for _ in range(30):
        if operation.get("status") == "DONE":
            if "error" in operation:
                raise RuntimeError("key_registration_failed")
            print(json.dumps({"ephemeral_ssh_key_registered": True, "expires": expires}))
            return
        time.sleep(2)
        operation = request(operation["selfLink"])
    raise TimeoutError("key_registration_timeout")


if __name__ == "__main__":
    main()
