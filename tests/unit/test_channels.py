from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.channels import MAX_INBOX_BYTES, ChannelHub, format_attention_notice
from pex_bridge.config import Settings
from pex_bridge.executor import ActionExecutor
from pex_bridge.store import Store
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.enums import Authority, HarnessType, PolicyVerdict
from pex_protocol.session import HarnessSession


def _session(**kwargs) -> HarnessSession:
    defaults = {
        "id": "cursor:sess-abc",
        "harness_type": HarnessType.CURSOR,
        "vendor_session_id": "sess-abc",
        "project_id": "demo",
        "last_activity": datetime.now(UTC),
    }
    defaults.update(kwargs)
    return HarnessSession(**defaults)


def _action(
    kind: InterventionType,
    payload: dict | None = None,
    *,
    rationale: str = "Need a human decision.",
) -> ProposedAction:
    return ProposedAction(
        type=kind,
        session_id="cursor:sess-abc",
        payload=payload or {},
        rationale=rationale,
        evidence=["event:observed"],
        confidence=0.8,
        risk=RiskLevel.LOW,
        authority_required=Authority.HUMAN,
    )


def test_attention_notice_uses_harness_label_not_vendor_ids():
    session = _session()
    notice = format_attention_notice(
        session,
        _action(
            InterventionType.ASK_HUMAN,
            {
                "question": (
                    "Should cursor:sess-abc / sess-abc keep the schema change?"
                )
            },
        ),
    )
    assert notice.startswith("PEX: Cursor needs you.")
    assert "sess-abc" not in notice
    assert "cursor:sess-abc" not in notice


def test_fork_probe_notice_names_the_harness_and_the_spend_risk():
    notice = format_attention_notice(
        _session(harness_type=HarnessType.OPENCODE, id="opencode:parent"),
        _action(InterventionType.FORK_PROBE),
    )
    assert notice.startswith("PEX: Opencode has two cheap approaches")
    assert "duplicate spend" in notice
    assert "opencode:parent" not in notice


def test_status_never_fakes_a_connected_messenger(tmp_path, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "x" * 40)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/fake")
    hub = ChannelHub(Settings(home=tmp_path, notify_file=True))
    status = hub.status()
    assert status["attention_policy"] == "human_decisions_only"
    by_id = {row["id"]: row for row in status["channels"]}
    assert by_id["file"]["configured"] is True
    assert by_id["file"]["connected"] is True
    for channel_id in ("telegram", "discord", "whatsapp", "slack"):
        assert by_id[channel_id]["configured"] is False
        assert by_id[channel_id]["connected"] is False
        assert "will not" in by_id[channel_id]["notes"].casefold()


def test_file_deliver_appends_redacted_jsonl(tmp_path):
    hub = ChannelHub(Settings(home=tmp_path, notify_file=True))
    outcome = hub.deliver("PEX: Cursor needs you. sk-testsecretvalue0123456789abcd", kind="notify")
    assert outcome == "notified:file"
    lines = (tmp_path / "channels" / "inbox.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "PEX: Cursor needs you." in lines[0]
    assert "sk-testsecretvalue0123456789abcd" not in lines[0]


def test_file_deliver_skips_empty_and_disabled(tmp_path):
    hub = ChannelHub(Settings(home=tmp_path, notify_file=True))
    assert hub.deliver("   ") == "notify_skipped_empty"
    disabled = ChannelHub(Settings(home=tmp_path, notify_file=False))
    assert disabled.deliver("PEX: Cursor needs you.") == "notification_not_configured"
    assert not (tmp_path / "channels" / "inbox.jsonl").exists()


def test_inbox_full_does_not_truncate_or_overwrite(tmp_path):
    hub = ChannelHub(Settings(home=tmp_path, notify_file=True))
    path: Path = hub.inbox_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * MAX_INBOX_BYTES)
    assert hub.deliver("PEX: Cursor needs you.") == "notify_inbox_full"
    assert path.stat().st_size == MAX_INBOX_BYTES


@pytest.mark.asyncio
async def test_notify_action_writes_the_local_inbox(tmp_path):
    store = Store(tmp_path / "pex.sqlite")
    await store.connect()
    try:
        adapters = AdapterRegistry()
        source = adapters.synthetic.seed_session(
            vendor_id="notify-source",
            project_id=str(tmp_path),
            cwd=str(tmp_path),
        )
        await store.upsert_session(source)
        hub = ChannelHub(Settings(home=tmp_path, notify_file=True))
        executor = ActionExecutor(adapters, store, channels=hub)
        action = _action(
            InterventionType.NOTIFY,
            {"text": "PEX: Cursor needs you."},
        )
        action.session_id = source.id
        assert await executor.execute(action, PolicyVerdict.ALLOW) == "notified:file"
        inbox = (tmp_path / "channels" / "inbox.jsonl").read_text(encoding="utf-8")
        assert "PEX: Cursor needs you." in inbox
        empty = _action(InterventionType.NOTIFY, {"text": "  "})
        empty.session_id = source.id
        assert await executor.execute(empty, PolicyVerdict.ALLOW) == "notify_skipped_empty"
        missing = ActionExecutor(adapters, store, channels=None)
        assert (
            await missing.execute(action, PolicyVerdict.ALLOW)
            == "notification_not_configured"
        )
    finally:
        await store.close()
