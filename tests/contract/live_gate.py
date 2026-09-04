"""Explicit action-time authorization gates for live contract tests."""

from __future__ import annotations

import os

import pytest


def require_live_authorization(*flags: str) -> None:
    """Skip unless every named live-side-effect flag is exactly ``1``."""
    missing = [flag for flag in flags if os.environ.get(flag) != "1"]
    if missing:
        rendered = ", ".join(f"{flag}=1" for flag in missing)
        pytest.skip(f"explicit live authorization required; set {rendered} only for this live run")
