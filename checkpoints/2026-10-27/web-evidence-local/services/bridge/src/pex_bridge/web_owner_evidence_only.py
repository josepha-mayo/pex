"""Explicit paired-event projection when no bridge workspace exists."""

from datetime import UTC, datetime
from pathlib import Path

from pex_bridge.web_owner_evidence import read_evidence


class OwnerEvidenceReader:
    def __init__(self, event_path: Path):
        if not isinstance(event_path, Path) or not event_path.is_absolute():
            raise ValueError("explicit absolute event path required")
        self.event_path = event_path

    async def read_workspace(self) -> dict:
        return {
            "schema": "pex.owner-workspace.v1",
            "observed_at": datetime.now(UTC).isoformat(),
            "run_evidence": read_evidence(self.event_path),
            "sessions": [],
            "goals": [],
            "truncated": {"sessions": False, "goals": False},
        }
