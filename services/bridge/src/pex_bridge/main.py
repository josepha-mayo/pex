from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
from pathlib import Path

import uvicorn

from pex_bridge.config import normalize_loopback_host

EXPECTED_BUNDLED_PET_IDS = (
    "pex",
    "ledger",
    "mesh",
    "nudge",
    "drift",
    "quiet",
    "ember",
    "von",
)


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _start_parent_watchdog(pid: int) -> None:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        wait_for_single_object = kernel32.WaitForSingleObject
        wait_for_single_object.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        wait_for_single_object.restype = wintypes.DWORD
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL
        parent_handle = open_process(0x00100000, False, pid)  # SYNCHRONIZE
        if not parent_handle:
            raise OSError(ctypes.get_last_error(), "could not retain PEX desktop process")

        def watch_windows() -> None:
            try:
                wait_for_single_object(parent_handle, 0xFFFFFFFF)
            finally:
                close_handle(parent_handle)
            os._exit(0)

        threading.Thread(
            target=watch_windows,
            name="pex-parent-watchdog",
            daemon=True,
        ).start()
        return

    def watch() -> None:
        while _process_is_alive(pid):
            time.sleep(1)
        os._exit(0)

    threading.Thread(target=watch, name="pex-parent-watchdog", daemon=True).start()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def bundled_pet_inventory() -> dict[str, object]:
    """Return a path-free proof of the exact pet resources in this runtime."""

    from pex_bridge.pets import PetSettings, catalog, import_codex_pet

    pets = catalog(PetSettings())
    ids = tuple(pet.id for pet in pets)
    if ids != EXPECTED_BUNDLED_PET_IDS:
        raise RuntimeError(
            "bundled pet roster mismatch: "
            f"expected {EXPECTED_BUNDLED_PET_IDS!r}, got {ids!r}"
        )

    inventory: list[dict[str, object]] = []
    for pet in pets:
        if not pet.atlas_ready or not pet.spritesheet:
            raise RuntimeError(f"bundled pet atlas is unavailable: {pet.id}")
        sheet = Path(pet.spritesheet).resolve(strict=True)
        manifest = (sheet.parent / "pet.json").resolve(strict=True)
        imported = import_codex_pet(sheet.parent)
        if imported.id != f"import:{pet.id}":
            raise RuntimeError(f"bundled pet manifest id mismatch: {pet.id}")
        inventory.append(
            {
                "id": pet.id,
                "manifest_sha256": _sha256(manifest),
                "spritesheet_sha256": _sha256(sheet),
                "spritesheet_bytes": sheet.stat().st_size,
            }
        )
    return {"version": 1, "pets": inventory}


def main() -> None:
    parser = argparse.ArgumentParser(description="PEX local bridge")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument(
        "--verify-bundle",
        action="store_true",
        help="verify and print the exact embedded pet inventory, then exit",
    )
    args = parser.parse_args()
    if args.verify_bundle:
        print(json.dumps(bundled_pet_inventory(), separators=(",", ":")))
        return

    from pex_bridge.app import create_app, state

    parent_pid = os.environ.pop("PEX_DESKTOP_PARENT_PID", "").strip()
    if parent_pid:
        try:
            parsed_parent_pid = int(parent_pid)
        except ValueError:
            parser.error("PEX_DESKTOP_PARENT_PID must be a positive integer")
        if os.name != "nt" and not _process_is_alive(parsed_parent_pid):
            parser.error("PEX desktop parent process is not alive")
        try:
            _start_parent_watchdog(parsed_parent_pid)
        except OSError as exc:
            parser.error(str(exc))

    # The desktop passes its operator bearer only to this owned sidecar. Settings
    # has already validated and copied it into bridge-owned memory, so scrub the
    # inherited environment before any adapter can spawn a worker process.
    if state.token:
        from pex_bridge.adapters.cursor import set_internal_bridge_token

        set_internal_bridge_token(state.token)
        # Never leave the operator bearer in inherited process env for workers.
        os.environ.pop("PEX_TOKEN", None)

    try:
        host = normalize_loopback_host(args.host or state.settings.host)
    except ValueError as exc:
        parser.error(str(exc))
    port = args.port if args.port is not None else state.settings.port
    if not 1 <= port <= 65_535:
        parser.error("PEX bridge port must be between 1 and 65535")
    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
