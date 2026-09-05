"""Local evidence authority with temporary directories and no model/provider I/O."""

import asyncio
import json
from contextvars import copy_context
from threading import Event

import pytest
from pex_bridge.local_origin_config import save_local_origin_choice
from pex_bridge.local_workspace import measure_local_directory
from pex_bridge.workspace_binding import WorkspaceBinding, require_current_workspace
from pex_protocol.project_identity import ProjectLocator, ProjectOrigin
from pex_supervisor import workspace as workspace_module
from pex_supervisor.evidence_observations import EvidenceObservationCollector
from pex_supervisor.evidence_tools import build_evidence_tools, workspace_evidence_guard
from test_supervisor_loop import _request


@pytest.fixture
def bound(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "report.txt").write_text("VALID_CONTENT", encoding="utf-8")
    origin_path = tmp_path / "origin.json"
    choice = save_local_origin_choice(
        origin_path,
        ProjectOrigin(namespace="machine", host="explicit-test-origin"),
        expected_revision=None,
        expected_choice_id=None,
    )
    directory = measure_local_directory(str(root))
    binding = WorkspaceBinding(
        project_id="p",
        project_binding="identity:test-project",
        origin_choice=choice,
        directory=directory,
        locator=ProjectLocator.path(
            directory.cwd,
            platform=directory.platform,
            origin=choice.origin,
            physical=directory.physical,
        ),
    )
    request = _request(0.1)
    request.session.cwd = directory.cwd
    request.session.metadata["workspace_binding"] = binding.model_dump(mode="json")
    collector = EvidenceObservationCollector(request, stage="main", invocation_id="tool-review")
    tools = {
        tool.tool_name: tool for tool in build_evidence_tools(request, [], collector=collector)
    }
    return request, tools, collector, binding, origin_path, root


def check(bound):
    require_current_workspace(bound[3], bound[4])


def unavailable(output, collector):
    assert json.loads(output)["error"] == "workspace_authority_unavailable"
    assert "STALE_CONTENT" not in output
    assert "STALE_CONTENT" not in "".join(item.output for item in collector.observations)


@pytest.mark.parametrize(
    "name", ["inspect_workspace", "inspect_git", "inspect_file", "inspect_artifact"]
)
def test_bound_tools_without_trusted_invocation_never_read(bound, monkeypatch, name):
    def forbidden(*args, **kwargs):
        pytest.fail("untrusted local read")

    for operation in ("snapshot", "git_snapshot", "read_visible", "artifact_tails"):
        monkeypatch.setattr(workspace_module, operation, forbidden)
    unavailable(
        bound[1][name](path="report.txt") if name == "inspect_file" else bound[1][name](), bound[2]
    )


@pytest.mark.parametrize(
    "field", ["id", "vendor_session_id", "project_id", "cwd", "workspace_binding", "drop"]
)
def test_guard_cannot_be_reused_with_different_target(bound, monkeypatch, field):
    original = bound[0].session.model_copy(deep=True)
    if field == "workspace_binding":
        bound[0].session.metadata[field]["project_id"] = "other-project"
    elif field == "drop":
        bound[0].session.metadata.clear()
    else:
        setattr(bound[0].session, field, "other-target")
    monkeypatch.setattr(
        workspace_module, "read_visible", lambda *a, **k: pytest.fail("wrong target")
    )
    with workspace_evidence_guard(original, lambda: check(bound)):
        unavailable(bound[1]["inspect_file"](path="report.txt"), bound[2])


@pytest.mark.parametrize("change", ["directory", "origin"])
@pytest.mark.parametrize(
    "name,operation,payload",
    [
        ("inspect_workspace", "snapshot", {"files": ["STALE_CONTENT"]}),
        ("inspect_git", "git_snapshot", {"available": True, "diff": "STALE_CONTENT"}),
        ("inspect_file", "read_visible", {"text": "STALE_CONTENT"}),
        ("inspect_artifact", "artifact_tails", [{"path": "report.txt", "text": "STALE_CONTENT"}]),
    ],
)
def test_changed_authority_during_read_discards_output(
    bound, monkeypatch, change, name, operation, payload
):
    calls = []

    def changed(*args, **kwargs):
        calls.append(operation)
        if change == "directory":
            bound[5].rename(bound[5].with_name("preserved-original"))
            bound[5].mkdir()
        else:
            choice = bound[3].origin_choice
            save_local_origin_choice(
                bound[4],
                choice.origin,
                expected_revision=choice.revision,
                expected_choice_id=choice.choice_id,
            )
        return payload

    monkeypatch.setattr(workspace_module, operation, changed)
    with workspace_evidence_guard(bound[0].session, lambda: check(bound)):
        output = bound[1][name](path="report.txt") if name == "inspect_file" else bound[1][name]()
    assert calls == [operation]
    unavailable(output, bound[2])


def test_regular_file_content_edit_does_not_revoke_directory(bound):
    with workspace_evidence_guard(bound[0].session, lambda: check(bound)):
        before = bound[1]["inspect_file"](path="report.txt")
        (bound[5] / "report.txt").write_text("VALID_EDIT", encoding="utf-8")
        after = bound[1]["inspect_file"](path="report.txt")
    assert "VALID_CONTENT" in before
    assert "VALID_EDIT" in after
    assert len(bound[2].observations) == 2


def test_inherited_context_is_revoked_after_exit(bound, monkeypatch):
    with workspace_evidence_guard(bound[0].session, lambda: check(bound)):
        inherited = copy_context()
    monkeypatch.setattr(
        workspace_module, "read_visible", lambda *a, **k: pytest.fail("revoked read")
    )
    unavailable(inherited.run(bound[1]["inspect_file"], path="report.txt"), bound[2])


async def test_cancelled_invocation_discards_inflight_thread_result(bound, monkeypatch):
    entered, release = Event(), Event()
    tasks = []

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return {"text": "STALE_CONTENT"}

    monkeypatch.setattr(workspace_module, "read_visible", delayed)

    async def invoke():
        with workspace_evidence_guard(bound[0].session, lambda: check(bound)):
            task = asyncio.create_task(
                asyncio.to_thread(bound[1]["inspect_file"], path="report.txt")
            )
            tasks.append(task)
            return await asyncio.shield(task)

    invocation = asyncio.create_task(invoke())
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        invocation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await invocation
    finally:
        release.set()
        await asyncio.gather(invocation, return_exceptions=True)
    unavailable(await asyncio.wait_for(tasks[0], 5), bound[2])


def test_read_failure_after_authority_loss_is_sanitized(bound, monkeypatch):
    def failed(*args, **kwargs):
        bound[5].rename(bound[5].with_name("preserved-original"))
        raise OSError("STALE_CONTENT")

    monkeypatch.setattr(workspace_module, "read_visible", failed)
    with workspace_evidence_guard(bound[0].session, lambda: check(bound)):
        unavailable(bound[1]["inspect_file"](path="report.txt"), bound[2])


@pytest.mark.parametrize("change", ["directory", "origin"])
def test_already_stale_workspace_has_zero_reads(bound, monkeypatch, change):
    if change == "directory":
        bound[5].rename(bound[5].with_name("preserved-original"))
        bound[5].mkdir()
    else:
        choice = bound[3].origin_choice
        save_local_origin_choice(
            bound[4], choice.origin,
            expected_revision=choice.revision, expected_choice_id=choice.choice_id,
        )
    monkeypatch.setattr(
        workspace_module, "read_visible", lambda *a, **k: pytest.fail("stale read"),
    )
    with workspace_evidence_guard(bound[0].session, lambda: check(bound)):
        unavailable(bound[1]["inspect_file"](path="report.txt"), bound[2])


def test_guard_exception_and_prefetched_content_do_not_escape(bound):
    bound[0].scores.features["prefetched_evidence"] = {"files": ["STALE_CONTENT"]}

    def failed_check():
        raise ValueError("STALE_CONTENT")

    with workspace_evidence_guard(bound[0].session, failed_check):
        unavailable(bound[1]["inspect_workspace"](), bound[2])
