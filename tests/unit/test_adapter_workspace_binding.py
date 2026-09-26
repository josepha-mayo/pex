from __future__ import annotations

import pytest
from pex_bridge.adapters.base import preserve_bridge_state, session_binding_matches
from pex_bridge.adapters.http_json import MemoryHttpTransport
from pex_bridge.adapters.opencode import OpenCodeAdapter
from pex_protocol.enums import HarnessType
from pex_protocol.session import HarnessSession


def _worker(cwd: str, project_id: str) -> HarnessSession:
    return HarnessSession(
        id="opencode:binding",
        vendor_session_id="binding",
        harness_type=HarnessType.OPENCODE,
        cwd=cwd,
        project_id=project_id,
        goal_id="goal-original",
        supervision_paused=True,
    )


@pytest.mark.parametrize(
    ("cwd", "project_id", "observed_cwd", "observed_project", "matches"),
    [
        ("/work/PEX", "project-a", "/work/pex", "project-a", False),
        ("/work/pex", "project:PEX", "/work/pex", "project:pex", False),
        ("/work/pex", "project-a", "/work/pex", "project-a", True),
        ("/work/a/../pex", "project-a", "/work/pex", "project-a", False),
        (r"D:\work\pex", r"D:\work\pex", "d:/WORK/pex", "d:/WORK/pex", True),
    ],
)
def test_adapter_binding_and_rediscovery_keep_exact_workspace_identity(
    cwd, project_id, observed_cwd, observed_project, matches
):
    bound = _worker(cwd, project_id)
    supplied = bound.model_copy(update={"cwd": observed_cwd, "project_id": observed_project})
    assert session_binding_matches(bound, supplied, harness_type=HarnessType.OPENCODE) is matches
    assert preserve_bridge_state(
        bound, cwd=observed_cwd, project_id=observed_project
    ) == (("goal-original", True) if matches else (None, False))


@pytest.mark.asyncio
async def test_opencode_correction_cannot_use_case_distinct_posix_caller_binding():
    transport = MemoryHttpTransport()
    adapter = OpenCodeAdapter(transport)
    bound = _worker("/work/PEX", "project-a")
    adapter.sessions[bound.id] = bound
    supplied = bound.model_copy(update={"cwd": "/work/pex"})
    assert await adapter.send_message(supplied, "Finish the missing artifact.") is False
    assert adapter.inbox == {}
    assert transport.calls == []
