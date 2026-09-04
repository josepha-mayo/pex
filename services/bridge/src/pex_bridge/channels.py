"""Build spec §6.6 remote channels with the same attention policy as the deck.

Telegram, Discord, WhatsApp, and Slack stay unconfigured until the operator
supplies a real adapter. The local inbox is the only implemented delivery path.
It never messages a worker and never fakes a connected messenger.
"""

from __future__ import annotations

import json
from typing import Any

from pex_protocol.actions import InterventionType, ProposedAction
from pex_protocol.session import HarnessSession

from pex_bridge.config import Settings
from pex_bridge.secrets import redact_text
from pex_bridge.store import utcnow

MAX_NOTICE_CHARS = 2_000
MAX_INBOX_BYTES = 1_048_576
_REMOTE_UNAVAILABLE = (
    (
        "telegram",
        "Telegram",
        "No bot token. Will not fake a connected Telegram bot.",
    ),
    (
        "discord",
        "Discord",
        "No webhook. Will not fake a connected Discord channel.",
    ),
    (
        "whatsapp",
        "WhatsApp",
        "Not implemented. Will not scrape WhatsApp Web.",
    ),
    (
        "slack",
        "Slack",
        "No workspace token. Will not fake a connected Slack app.",
    ),
)


def _harness_label(session: HarnessSession) -> str:
    raw = session.harness_type.value.replace("_", " ").strip() or "agent"
    return raw[:1].upper() + raw[1:]


def format_attention_notice(session: HarnessSession, action: ProposedAction) -> str:
    """Human-facing remote copy. Spec examples may start with PEX:; workers must not."""

    harness = _harness_label(session)
    question = str(
        action.payload.get("question")
        or action.payload.get("text")
        or action.rationale
        or "A decision is waiting in PEX."
    )
    cleaned, _ = redact_text(question)
    cleaned = " ".join((cleaned or "").split())[:800]
    if session.id and session.id in cleaned:
        cleaned = cleaned.replace(session.id, harness)
    if session.vendor_session_id:
        cleaned = cleaned.replace(str(session.vendor_session_id), harness)
    kind = action.type
    if kind == InterventionType.FORK_PROBE:
        return (
            f"PEX: {harness} has two cheap approaches ready to probe in isolation. "
            "This can duplicate spend. Choose whether to fork, or tell me your rule."
        )[:MAX_NOTICE_CHARS]
    if kind == InterventionType.STOP_AGENT:
        return (
            f"PEX: {harness} should be stopped. This can discard active state. "
            "Confirm dispose or keep the worker."
        )[:MAX_NOTICE_CHARS]
    if kind == InterventionType.START_AGENT:
        return (
            f"PEX: {harness} wants to start another worker. "
            "Confirm start or keep the current session."
        )[:MAX_NOTICE_CHARS]
    return f"PEX: {harness} needs you. {cleaned}".strip()[:MAX_NOTICE_CHARS]


class ChannelHub:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.inbox_path = settings.data_dir / "channels" / "inbox.jsonl"

    def status(self) -> dict[str, Any]:
        file_on = bool(self.settings.notify_file)
        channels = [
            {
                "id": "file",
                "label": "Local inbox",
                "configured": file_on,
                "connected": file_on,
                "notes": (
                    f"Writes attention notices to {self.inbox_path}."
                    if file_on
                    else "Local inbox disabled. Remote messengers stay unconfigured."
                ),
            }
        ]
        for channel_id, label, notes in _REMOTE_UNAVAILABLE:
            channels.append(
                {
                    "id": channel_id,
                    "label": label,
                    "configured": False,
                    "connected": False,
                    "notes": notes,
                }
            )
        return {
            "attention_policy": "human_decisions_only",
            "channels": channels,
        }

    def deliver(
        self,
        text: str,
        *,
        kind: str = "notify",
        idempotency_key: str | None = None,
    ) -> str:
        cleaned, _ = redact_text(text)
        cleaned = (cleaned or "").strip()[:MAX_NOTICE_CHARS]
        if not cleaned:
            return "notify_skipped_empty"
        if not self.settings.notify_file:
            return "notification_not_configured"
        path = self.inbox_path
        path.parent.mkdir(parents=True, exist_ok=True)
        if idempotency_key:
            key = idempotency_key[:256]
            if path.exists():
                # The inbox is capped at 1 MiB, so an exact replay scan stays
                # bounded and closes the crash window between append and the
                # intervention-ledger update.
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        prior = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if isinstance(prior, dict) and prior.get("idempotency_key") == key:
                        return "notified:file"
        else:
            key = None
        encoded = (
            json.dumps(
                {
                    "ts": utcnow().isoformat(),
                    "kind": kind[:64],
                    "text": cleaned,
                    **({"idempotency_key": key} if key else {}),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        )
        extra = len(encoded.encode("utf-8"))
        current = path.stat().st_size if path.exists() else 0
        if current >= MAX_INBOX_BYTES or current + extra > MAX_INBOX_BYTES:
            return "notify_inbox_full"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(encoded)
        return "notified:file"

    def deliver_attention(
        self,
        session: HarnessSession,
        action: ProposedAction,
        *,
        idempotency_key: str | None = None,
    ) -> str:
        return self.deliver(
            format_attention_notice(session, action),
            kind="decision",
            idempotency_key=idempotency_key,
        )
