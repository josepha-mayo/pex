"""Actual loopback TLS test against real event file; optional --browser, no recording."""

import json
import ssl
import subprocess
import sys
import time
from pathlib import Path

import httpx

command = [
    sys.executable,
    "serve_owner_evidence.py",
    "--events",
    str(Path("../runtime-private/pex-pilot-20261027/run-01/events.jsonl").resolve()),
    "--owner-secret-file",
    "local-private/owner.secret",
    "--tls-cert",
    "local-private/cert.pem",
    "--tls-key",
    "local-private/key.pem",
]
process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    with httpx.Client(
        verify=ssl.create_default_context(cafile="local-private/cert.pem"),
        trust_env=False,
        base_url="https://127.0.0.1:7443",
    ) as client:
        for _ in range(30):
            try:
                result = client.get("/")
                break
            except httpx.ConnectError:
                time.sleep(0.1)
        assert result.status_code == 200
        assert client.get("/owner/workspace").status_code == 401
        result = client.post(
            "/owner/auth/login",
            headers={"Origin": "https://127.0.0.1:7443"},
            json={"owner_secret": Path("local-private/owner.secret").read_text()},
        )
        assert result.status_code == 200
        evidence = client.get("/owner/workspace").json()["run_evidence"]
        assert evidence["state"] == "recorded"
        print("Verified certificate TLS + auth + real metadata:", json.dumps(evidence))
    if "--browser" in sys.argv:
        subprocess.run(["node", "browser_check.cjs"], check=True, timeout=40)
finally:
    process.terminate()
    process.wait(timeout=10)
