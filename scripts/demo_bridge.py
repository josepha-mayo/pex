"""Test-scoped demo bridge for the PEX browser/desktop development flow.

Serves the real bridge app on loopback with ``require_auth=False`` so the
vite development UI (which cannot read the desktop bearer) can drive real
supervision. This is intentionally the same mechanism the e2e fixtures use;
it is not the production path — the packaged desktop app always uses an
operator bearer.

Safety posture, matching ``Settings.for_test`` semantics:
- loopback only (127.0.0.1);
- a dedicated PEX_HOME (default ``build/demo/pex-home``) keeps the throwaway
  profile separate from the operator's real ``~/.pex``;
- unauthenticated settings are only constructible through the process-local
  ``Settings.for_test`` gate, so no ambient environment can widen this.

Environment:
    PEX_DEMO_HOME          override the demo PEX_HOME directory
    PEX_DEMO_PORT          bridge port (default 7420)
    PEX_OPENCODE_URL       OpenCode server the adapter should observe
    PEX_CLOUD_REASONING    "true" enables bounded semantic supervisor
                           dispatches for BYOK demos (default off)
    PEX_SUPERVISOR_MAX_DISPATCHES_PER_SESSION
                           dispatch cap when cloud reasoning is on
"""

from __future__ import annotations

import os
from pathlib import Path

RUN_ROOT = Path(os.environ.get("PEX_DEMO_HOME", Path(__file__).resolve().parent.parent / "build" / "demo"))
PEX_HOME = RUN_ROOT / "pex-home" if RUN_ROOT.name != "pex-home" else RUN_ROOT
PEX_HOME.mkdir(parents=True, exist_ok=True)

os.environ["PEX_HOME"] = str(PEX_HOME)
os.environ.setdefault("PEX_AUTONOMY", "manage")

_PORT = int(os.environ.get("PEX_DEMO_PORT", "7420"))
_CLOUD = os.environ.get("PEX_CLOUD_REASONING", "").strip().lower() in {"1", "true", "yes"}
_MAX_DISPATCHES = int(os.environ.get("PEX_SUPERVISOR_MAX_DISPATCHES_PER_SESSION", "3"))
_OPENCODE_URL = os.environ.get("PEX_OPENCODE_URL", "http://127.0.0.1:4096")

import uvicorn  # noqa: E402

from pex_bridge.app import create_app, state  # noqa: E402
from pex_bridge.config import Settings  # noqa: E402

state.settings = Settings.for_test(
    require_auth=False,
    home=PEX_HOME,
    autonomy="manage",
    cloud_reasoning=_CLOUD,
    supervisor_max_dispatches_per_session=_MAX_DISPATCHES,
    opencode_url=_OPENCODE_URL,
)

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=_PORT, log_level="info",
                ws_per_message_deflate=False)
