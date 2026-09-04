from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

HOOK = Path(__file__).resolve().parents[2] / "integrations" / "cursor-hook" / "pex_cursor_hook.py"


def _load_hook(name: str):
    spec = importlib.util.spec_from_file_location(name, HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _packet(message: str, conversation_id: str = "conversation-ack") -> dict[str, str]:
    return {
        "schema": "pex.cursor-hook-delivery.v1",
        "preparation_id": "preparation-1",
        "intervention_id": "intervention-1",
        "trigger_event_id": "event-1",
        "target_session_id": f"cursor:{conversation_id}",
        "vendor_session_id": conversation_id,
        "goal_id": "goal-1",
        "message_sha256": hashlib.sha256(message.encode("utf-8")).hexdigest(),
        "nonce": "a" * 64,
    }


def _payload(conversation_id: str = "conversation-ack") -> dict:
    return {
        "hook_event_name": "stop",
        "conversation_id": conversation_id,
        "workspace_roots": ["C:/project"],
        "cwd": "C:/project",
    }


def _bridge_body(message: str, packet: object | None = None, *, include_packet: bool = True) -> str:
    body = {"followup_message": message}
    if include_packet:
        body["pex_hook_delivery"] = packet
    return json.dumps(body)


def _prepare_main(monkeypatch, hook, payload: dict, bridge_body: str, output) -> list[str]:
    events: list[str] = []
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode("utf-8"))),
    )
    monkeypatch.setattr(hook.sys, "stdout", output)
    monkeypatch.setattr(hook, "record_hook_activity", lambda *_: None)
    monkeypatch.setattr(hook, "record_stop_drop", lambda *_: None)
    monkeypatch.setattr(hook, "record_stop_delivery", lambda *_: events.append("drop-receipt"))
    monkeypatch.setattr(hook, "_load_isolated_control", lambda *_: None)
    monkeypatch.setattr(hook, "_cwd_in_isolated_workspace_tree", lambda *_: False)
    monkeypatch.setattr(hook, "_request", lambda *_: object())
    monkeypatch.setattr(hook, "_post", lambda *_: bridge_body)
    return events


def test_valid_packet_posts_private_ack_only_after_stdout_flush(monkeypatch):
    hook = _load_hook("cursor_delivery_ack_valid")
    payload = _payload()
    message = "Inspect the failing integration test."
    packet = _packet(message)
    bridge_body = _bridge_body(message, packet)
    events: list[str] = []

    class Output(io.StringIO):
        def flush(self):
            events.append("flush")
            super().flush()

    output = Output()
    receipt_events = _prepare_main(monkeypatch, hook, payload, bridge_body, output)

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return b"{}"

    class Opener:
        def open(self, request, *, timeout):
            assert events == ["flush"]
            events.append("ack")
            assert timeout == hook.DELIVERY_ACK_TIMEOUT_SECONDS
            assert timeout <= 1.0
            assert request.full_url == "http://127.0.0.1:7420/v1/hooks/cursor"
            ack = json.loads(request.data.decode("utf-8"))
            assert ack == {
                "hook_event_name": "pexDeliveryReceipt",
                "conversation_id": payload["conversation_id"],
                "workspace_roots": payload["workspace_roots"],
                "receipt": packet,
                "delivery_evidence": "hook_stdout_flushed",
            }
            return Response()

    def build_opener(handler):
        assert isinstance(handler, hook._NoRedirectHandler)
        return Opener()

    monkeypatch.setattr(hook.urllib.request, "build_opener", build_opener)
    hook.main()

    emitted = output.getvalue()
    assert json.loads(emitted) == {"followup_message": message}
    assert "pex_hook_delivery" not in emitted
    assert packet["nonce"] not in emitted
    assert receipt_events == ["drop-receipt"]
    assert events == ["flush", "ack"]


def test_private_packet_is_absent_from_opt_in_benchmark_drop(tmp_path, monkeypatch):
    monkeypatch.setenv("PEX_CURSOR_STOP_DROP", str(tmp_path / "drops"))
    hook = _load_hook("cursor_delivery_ack_private_drop")
    payload = _payload()
    message = "Capture only the sanitized follow-up evidence."
    packet = _packet(message)
    packet["preparation_id"] = "private-preparation-marker"
    packet["nonce"] = "b" * 64
    output = io.StringIO()
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode("utf-8"))),
    )
    monkeypatch.setattr(hook.sys, "stdout", output)
    monkeypatch.setattr(hook, "_load_isolated_control", lambda *_: None)
    monkeypatch.setattr(hook, "_cwd_in_isolated_workspace_tree", lambda *_: False)
    monkeypatch.setattr(hook, "_request", lambda *_: object())
    monkeypatch.setattr(hook, "_post", lambda *_: _bridge_body(message, packet))
    monkeypatch.setattr(hook, "_post_delivery_ack", lambda *_: True)

    hook.main()

    assert "pex_hook_delivery" not in output.getvalue()
    drops = list((tmp_path / "drops").glob("*.json"))
    assert len(drops) == 2
    journal = "\n".join(path.read_text(encoding="utf-8") for path in drops)
    assert "pex_hook_delivery" not in journal
    assert packet["preparation_id"] not in journal
    assert packet["nonce"] not in journal


def test_broken_stdout_flush_never_posts_ack(monkeypatch):
    hook = _load_hook("cursor_delivery_ack_broken_pipe")
    payload = _payload()
    message = "Continue with the exact verification."

    class Output(io.StringIO):
        def flush(self):
            raise BrokenPipeError("Cursor pipe closed")

    output = Output()
    receipts = _prepare_main(
        monkeypatch,
        hook,
        payload,
        _bridge_body(message, _packet(message)),
        output,
    )
    ack_calls: list[object] = []
    monkeypatch.setattr(hook, "_post_delivery_ack", lambda *_: ack_calls.append(object()))

    with pytest.raises(BrokenPipeError, match="Cursor pipe closed"):
        hook.main()

    assert ack_calls == []
    assert receipts == []


def test_partial_stdout_write_flushes_but_records_neither_delivery_nor_ack(monkeypatch):
    hook = _load_hook("cursor_delivery_ack_partial_write")
    payload = _payload()
    message = "Only a complete stdout write may produce a receipt."
    flushes: list[object] = []

    class PartialOutput(io.StringIO):
        def write(self, value):
            partial = value[: max(1, len(value) // 2)]
            super().write(partial)
            return len(partial)

        def flush(self):
            flushes.append(object())
            super().flush()

    output = PartialOutput()
    receipts = _prepare_main(
        monkeypatch,
        hook,
        payload,
        _bridge_body(message, _packet(message)),
        output,
    )
    ack_calls: list[object] = []
    monkeypatch.setattr(hook, "_post_delivery_ack", lambda *_: ack_calls.append(object()))

    hook.main()

    assert len(flushes) == 1
    assert len(output.getvalue()) < len(json.dumps({"followup_message": message}))
    assert receipts == []
    assert ack_calls == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda packet: packet.update({"unexpected": "field"}),
        lambda packet: packet.update({"target_session_id": "cursor:other"}),
        lambda packet: packet.update({"vendor_session_id": "other"}),
        lambda packet: packet.update({"message_sha256": "0" * 64}),
        lambda packet: packet.update({"nonce": "A" * 64}),
        lambda packet: packet.update({"goal_id": 123}),
        lambda packet: packet.update({"preparation_id": "x" * 513}),
    ],
)
def test_invalid_or_cross_session_packet_suppresses_followup_and_ack(monkeypatch, mutate):
    hook = _load_hook(f"cursor_delivery_ack_invalid_{id(mutate)}")
    payload = _payload()
    message = "Do the bound follow-up."
    packet = _packet(message)
    mutate(packet)
    output = io.StringIO()
    _prepare_main(monkeypatch, hook, payload, _bridge_body(message, packet), output)
    ack_calls: list[object] = []
    monkeypatch.setattr(hook, "_post_delivery_ack", lambda *_: ack_calls.append(object()))

    hook.main()

    assert output.getvalue() == "{}"
    assert ack_calls == []


def test_legacy_response_emits_followup_without_ack(monkeypatch):
    hook = _load_hook("cursor_delivery_ack_legacy")
    payload = _payload()
    message = "Legacy follow-up remains compatible."
    output = io.StringIO()
    _prepare_main(
        monkeypatch,
        hook,
        payload,
        _bridge_body(message, include_packet=False),
        output,
    )
    ack_calls: list[object] = []
    monkeypatch.setattr(hook, "_post_delivery_ack", lambda *_: ack_calls.append(object()))

    hook.main()

    assert json.loads(output.getvalue()) == {"followup_message": message}
    assert ack_calls == []


def test_ack_failure_is_benign_and_is_not_retried(monkeypatch):
    hook = _load_hook("cursor_delivery_ack_failure")
    payload = _payload()
    message = "Follow up even if the private ACK endpoint fails."
    output = io.StringIO()
    _prepare_main(monkeypatch, hook, payload, _bridge_body(message, _packet(message)), output)
    calls: list[object] = []

    class Opener:
        def open(self, *_args, **_kwargs):
            calls.append(object())
            raise urllib.error.URLError("bridge closed")

    monkeypatch.setattr(hook.urllib.request, "build_opener", lambda *_: Opener())
    hook.main()

    assert len(calls) == 1
    assert json.loads(output.getvalue()) == {"followup_message": message}
    assert output.getvalue().count("followup_message") == 1


def test_ack_disables_redirects_and_does_not_retry(monkeypatch):
    hook = _load_hook("cursor_delivery_ack_redirect")
    payload = _payload()
    message = "No redirect target may receive the receipt."
    calls: list[object] = []

    class Opener:
        def open(self, request, **_kwargs):
            calls.append(request)
            raise urllib.error.HTTPError(
                request.full_url,
                302,
                "redirect blocked",
                {"Location": "http://127.0.0.1:9999/steal"},
                None,
            )

    def build_opener(handler):
        assert isinstance(handler, hook._NoRedirectHandler)
        assert handler.redirect_request(None, None, 302, "", {}, "http://elsewhere") is None
        return Opener()

    monkeypatch.setattr(hook.urllib.request, "build_opener", build_opener)
    assert hook._post_delivery_ack(payload, _packet(message)) is False
    assert len(calls) == 1


def test_schema2_isolated_stop_never_posts_production_ack(monkeypatch):
    hook = _load_hook("cursor_delivery_ack_isolated")
    payload = _payload()
    output = io.StringIO()
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode("utf-8"))),
    )
    monkeypatch.setattr(hook.sys, "stdout", output)
    control = {"schema_version": 2, "isolated_supervisor": True}
    monkeypatch.setattr(hook, "_load_isolated_control", lambda *_: control)
    monkeypatch.setattr(
        hook,
        "_run_isolated_supervisor",
        lambda *_: json.dumps({"followup_message": "Benchmark-only follow-up."}),
    )
    monkeypatch.setattr(hook, "record_hook_activity", lambda *_: None)
    monkeypatch.setattr(hook, "record_stop_drop", lambda *_: None)
    monkeypatch.setattr(hook, "record_stop_delivery", lambda *_: None)
    ack_calls: list[object] = []
    monkeypatch.setattr(hook, "_post_delivery_ack", lambda *_: ack_calls.append(object()))

    hook.main()

    assert ack_calls == []
    assert json.loads(output.getvalue()) == {"followup_message": "Benchmark-only follow-up."}
