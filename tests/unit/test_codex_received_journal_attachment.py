"""Real attachment manager and temporary SQLite; fake worker, no native launch."""
# ruff: noqa: F811 -- pytest fixture imported explicitly for this module.

import json
import sqlite3

import pytest
from pex_bridge.app import state
from pex_bridge.codex_received_journal import CodexReceivedJournalError
from test_codex_received_journal import read_rows
from test_codex_shared_attach import _confirm, _inspect, shared_client  # noqa: F401


@pytest.mark.asyncio
async def test_inspection_journal_precedes_vendor_reads_and_confirmation_does_not_relabel(
    shared_client,
):
    client, body, transports, _, _, _ = shared_client
    selected = await _inspect(client, body)
    journal = transports[0].receive_journal
    assert journal.inspection_id == selected["inspection_id"]
    assert journal.path == state.settings.home / "codex-received.sqlite"
    rows = read_rows(journal.path, "receive_attempts")
    provenance = json.loads(rows[0]["provenance_json"])
    assert provenance["requested_thread_id"] == body["thread_id"]
    assert provenance["requested_project_id"] == body["project_id"]
    assert provenance["requested_socket_path"] == body["socket_path"]
    assert provenance["workspace_binding_at_inspect"] == selected["workspace_binding"]
    assert provenance["scope"] == "connector_received_bytes_not_live_authority"
    assert "selected" not in provenance and "subscribed" not in provenance
    # Fake transport has no byte stream: no fabricated raw coverage is inserted.
    assert read_rows(journal.path) == []
    confirmed = await _confirm(client, selected)
    assert confirmed.status_code == 200, confirmed.text
    assert read_rows(journal.path, "receive_attempts") == rows


@pytest.mark.asyncio
async def test_journal_initialization_failure_starts_no_connector(shared_client, monkeypatch):
    import pex_bridge.codex_shared_attach as module

    client, body, transports, _, _, _ = shared_client
    calls = []

    def failed(*args, **kwargs):
        calls.append(kwargs["inspection_id"])
        raise CodexReceivedJournalError("fixture journal unavailable")

    monkeypatch.setattr(module, "CodexReceivedJournal", failed)
    # The direct manager call proves the failure boundary without an ASGI error
    # renderer hiding which operation failed. No transport factory was entered.
    with pytest.raises(CodexReceivedJournalError):
        await state.codex_shared_attachments.inspect(module.SharedCodexInspect(**body), state)
    assert len(calls) == 1 and len(calls[0]) == 32
    assert transports == []
    assert state.codex_shared_attachments.pending == {}


@pytest.mark.asyncio
async def test_failed_vendor_inspection_keeps_requested_attempt_not_live_authority(
    shared_client, monkeypatch
):
    import pex_bridge.codex_shared_attach as module

    _, body, transports, _, _, _ = shared_client

    async def failed(*args, **kwargs):
        raise ValueError("fixture vendor identity changed")

    monkeypatch.setattr(module.CodexExistingThreadSubscription, "inspect_thread", failed)
    with pytest.raises(ValueError, match="identity changed"):
        await state.codex_shared_attachments.inspect(module.SharedCodexInspect(**body), state)
    assert len(transports) == 1 and transports[0].closed
    rows = read_rows(transports[0].receive_journal.path, "receive_attempts")
    assert len(rows) == 1 and state.codex_shared_attachments.pending == {}


@pytest.mark.asyncio
async def test_unavailable_existing_journal_is_preserved(shared_client):
    import pex_bridge.codex_shared_attach as module

    _, body, transports, _, _, _ = shared_client
    path = state.settings.home / "codex-received.sqlite"
    # A foreign SQLite schema is not silently overwritten on failed creation.
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE receive_attempts (foreign_column TEXT)")
        connection.execute("INSERT INTO receive_attempts VALUES ('preserve me')")
        connection.commit()
    finally:
        connection.close()
    original_bytes = path.read_bytes()
    with pytest.raises(CodexReceivedJournalError):
        await state.codex_shared_attachments.inspect(module.SharedCodexInspect(**body), state)
    assert transports == []
    assert read_rows(path, "receive_attempts") == [{"foreign_column": "preserve me"}]
    assert path.read_bytes() == original_bytes
