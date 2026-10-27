"""Local-only TLS composition. Explicit files; no bridge startup or providers."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for relative in (
    "services/bridge/src",
    "packages/protocol/src",
    "services/supervisor/src",
):
    sys.path.insert(0, str(ROOT / relative))

from pex_bridge.web_owner_auth import (  # noqa: E402
    OwnerAuthError,
    OwnerSessions,
    ProvisionedOwnerVerifier,
    WebOwnerConfig,
)
from pex_bridge.web_owner_evidence_only import OwnerEvidenceReader  # noqa: E402
from pex_bridge.web_owner_http import create_web_owner_auth_app  # noqa: E402


def read_secret(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError("owner secret must be a private owner-controlled regular file")
        secret = stream.read(45).decode("ascii").strip()
    import re

    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", secret):
        raise ValueError("invalid owner secret file")
    return secret


class LocalEvidenceApp:
    def __init__(self, *, origin: str, secret: str, events: Path):
        self.sessions = OwnerSessions(
            WebOwnerConfig(
                enabled=True,
                public_origin=origin,
                verifier=ProvisionedOwnerVerifier(
                    hashlib.sha256(secret.encode("ascii")).hexdigest()
                ),
            )
        )
        self.api = create_web_owner_auth_app(self.sessions, workspace=OwnerEvidenceReader(events))
        # Exact build inventory, loaded once; never map arbitrary URLs to disk.
        self.assets = {}
        for path in [
            ROOT / "dist-owner/owner.html",
            *(ROOT / "dist-owner/assets").iterdir(),
        ]:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
                raise ValueError("invalid static build")
            mime = {
                ".html": "text/html; charset=utf-8",
                ".js": "text/javascript",
                ".css": "text/css",
            }.get(path.suffix)
            if mime:
                route = "/owner.html" if path.suffix == ".html" else "/assets/" + path.name
                self.assets[route] = (path.read_bytes(), mime)
        self.assets["/"] = self.assets["/owner.html"]

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path", "").startswith("/owner/"):
            return await self.api(scope, receive, send)
        status, body, mime = 404, b"Not found", "text/plain"
        try:
            if scope.get("scheme") != "https":
                raise OwnerAuthError(403, "https_required")
            self.sessions.check_request_boundary(scope.get("headers", []), origin_required=False)
            path = scope.get("path", "")
            if (
                scope.get("method") == "GET"
                and not scope.get("query_string")
                and scope.get("raw_path", path.encode()) == path.encode()
                and path in self.assets
            ):
                status = 200
                body, mime = self.assets[path]
        except OwnerAuthError:
            status, body = 403, b"Denied"
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", mime.encode()),
                    (b"content-length", str(len(body)).encode()),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (
                        b"content-security-policy",
                        b"default-src 'none'; script-src 'self'; style-src 'self'; "
                        b"connect-src 'self'; form-action 'self'; base-uri 'none'; "
                        b"frame-ancestors 'none'",
                    ),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--owner-secret-file", required=True, type=Path)
    parser.add_argument("--tls-cert", required=True, type=Path)
    parser.add_argument("--tls-key", required=True, type=Path)
    parser.add_argument("--port", type=int, default=7443)
    args = parser.parse_args()
    if not args.events.is_absolute() or not 1024 <= args.port <= 65535:
        parser.error("absolute event path and nonprivileged port required")
    secret = read_secret(args.owner_secret_file)
    app = LocalEvidenceApp(
        origin=f"https://127.0.0.1:{args.port}", secret=secret, events=args.events
    )
    del secret
    import uvicorn

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        ssl_certfile=str(args.tls_cert),
        ssl_keyfile=str(args.tls_key),
        proxy_headers=False,
        access_log=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
