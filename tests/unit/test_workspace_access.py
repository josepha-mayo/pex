"""Actual published workspace read authority, without models or native workers."""

import asyncio
import threading

import pytest
from pex_bridge.workspace_access import workspace_read_check
from pex_bridge.workspace_binding import WorkspaceAuthorityError
from test_workspace_continuity_pipeline import _change_workspace
from test_workspace_continuity_pipeline import bound_pipeline as bound_pipeline


async def _call(check, context):
    if context == "async":
        check()  # Deliberately synchronous on the owning event loop.
    else:
        await asyncio.to_thread(check)


def _owned_workers():
    return {
        thread.ident for thread in threading.enumerate()
        if thread.name.startswith("pex-workspace-check")
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("context", ["sync", "async"])
async def test_full_workspace_check_valid_in_both_calling_contexts(bound_pipeline, context):
    bound = bound_pipeline
    witness = await bound.store.require_session_workspace_current(bound.adapter.session)
    check = workspace_read_check(bound.store, bound.adapter.session, witness)
    before = _owned_workers()
    await _call(check, context)
    (bound.workspace / "ordinary-edit").mkdir()
    await _call(check, context)
    assert _owned_workers() == before
    assert bound.snapshots == [] and bound.supervisor_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("context", ["sync", "async"])
@pytest.mark.parametrize("change", ["directory", "origin", "corrupt_origin", "locator", "session"])
async def test_full_workspace_check_rejects_revoked_publication(
    bound_pipeline, context, change,
):
    bound = bound_pipeline
    witness = await bound.store.require_session_workspace_current(bound.adapter.session)
    check = workspace_read_check(bound.store, bound.adapter.session, witness)
    before = _owned_workers()
    if change in {"directory", "origin"}:
        _change_workspace(bound, change)
    elif change == "corrupt_origin":
        bound.origin_path.write_text('{"invalid":true}', encoding="utf-8")
    elif change == "locator":
        await bound.store.db.execute(
            "DELETE FROM project_locators WHERE fingerprint = ?",
            (bound.workspace_binding.locator.fingerprint,),
        )
        await bound.store.db.commit()
    else:
        changed = bound.adapter.session.model_copy(deep=True)
        changed.vendor_session_id = "different-vendor-thread"
        await bound.store.db.execute(
            "UPDATE sessions SET vendor_session_id = ?, json = ? WHERE id = ?",
            (changed.vendor_session_id, changed.model_dump_json(), changed.id),
        )
        await bound.store.db.commit()
    with pytest.raises(WorkspaceAuthorityError):
        await _call(check, context)
    assert _owned_workers() == before
    assert bound.snapshots == [] and bound.supervisor_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("context", ["sync", "async"])
async def test_callback_freezes_session(bound_pipeline, context):
    bound = bound_pipeline
    session = bound.adapter.session.model_copy(deep=True)
    witness = await bound.store.require_session_workspace_current(session)
    check = workspace_read_check(bound.store, session, witness)
    session.id = "codex:other-thread"
    session.cwd = str(bound.workspace.parent)
    session.metadata.clear()
    await _call(check, context)
    assert bound.snapshots == [] and bound.supervisor_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("context", ["sync", "async"])
async def test_callback_rejects_cross_session_witness(bound_pipeline, context):
    bound = bound_pipeline
    witness = await bound.store.require_session_workspace_current(bound.adapter.session)
    different = bound.adapter.session.model_copy(deep=True)
    different.id = "codex:other-thread"
    check = workspace_read_check(bound.store, different, witness)
    with pytest.raises(WorkspaceAuthorityError):
        await _call(check, context)
