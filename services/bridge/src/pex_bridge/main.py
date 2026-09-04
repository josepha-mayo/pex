from __future__ import annotations

import argparse
import hashlib
import json
import os
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
