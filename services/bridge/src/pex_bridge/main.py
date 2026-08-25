from __future__ import annotations

import argparse

import uvicorn

from pex_bridge.app import create_app, state


def main() -> None:
    parser = argparse.ArgumentParser(description="PEX local bridge")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-auth", action="store_true")
    args = parser.parse_args()
    if args.no_auth:
        state.settings.require_auth = False
        state.token = None
    host = args.host or state.settings.host
    port = args.port or state.settings.port
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
