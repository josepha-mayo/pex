"""Durable, content-free Cursor observer rejection receipts."""

from __future__ import annotations

import pytest
from pex_bridge.store import Store


@pytest.mark.asyncio
async def test_rejection_receipt_is_idempotent_restart_durable_and_content_free(tmp_path):
    path = tmp_path / "pex.sqlite"
    store = Store(path)
    await store.connect()
    try:
        first = await store.record_cursor_inbox_rejection(
            file_identity=(17, 29),
            start=41,
            end=73,
            record_sha256="a" * 64,
            reason="invalid_hook_shape",
        )
        replay = await store.record_cursor_inbox_rejection(
            file_identity=(17, 29),
            start=41,
            end=73,
            record_sha256="a" * 64,
            reason="invalid_hook_shape",
        )
        assert replay == first
        assert set(first) == {
            "schema", "receipt_id", "file_identity", "start", "end",
            "record_sha256", "reason", "rejected_at",
        }
        assert first["schema"] == "pex.cursor-inbox-rejection.v1"
        assert first["file_identity"] == {"device": "17", "inode": "29"}
    finally:
        await store.close()

    reopened = Store(path)
    await reopened.connect()
    try:
        page = await reopened.list_cursor_inbox_rejections(limit=10, offset=0)
        assert page == {
            "schema": "pex.cursor-inbox-rejections.v1",
            "total": 1,
            "limit": 10,
            "offset": 0,
            "items": [first],
        }
    finally:
        await reopened.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("file_identity", (-1, 2)),
        ("start", -1),
        ("end", 41),
        ("record_sha256", "not-a-digest"),
        ("reason", "arbitrary_reason"),
    ],
)
async def test_rejection_receipt_rejects_unbounded_or_unknown_fields(tmp_path, field, value):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        arguments = {
            "file_identity": (17, 29),
            "start": 41,
            "end": 73,
            "record_sha256": "a" * 64,
            "reason": "invalid_hook_shape",
        }
        arguments[field] = value
        with pytest.raises(ValueError):
            await store.record_cursor_inbox_rejection(**arguments)
    finally:
        await store.close()
