from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "integrations" / "cursor-hook" / "pex_cursor_hook.py"


def _load_hook(name: str):
    spec = importlib.util.spec_from_file_location(name, HOOK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _schema2_control(tmp_path: Path, monkeypatch, arm: str):
    workspace = tmp_path / f"ws_{arm}"
    workspace.mkdir()
    search = tmp_path / "control-search"
    search.mkdir()
    private = tmp_path / "private" / arm
    spool = private / "receipts"
    spool.mkdir(parents=True)
    global_drop = tmp_path / "global-drop"
    monkeypatch.setenv("PEX_CURSOR_ISOLATED_CONTROL", str(search))
    monkeypatch.setenv("PEX_CURSOR_STOP_DROP", str(global_drop))
    binding = {
        "run_id": "capture-run",
        "arm": arm,
        "task": "public-task",
        "workspace": str(workspace.resolve()),
        "capture_nonce": "b" * 32,
        "prompt_sha256": "a" * 64,
    }
    control = {
        "schema_version": 2,
        "arm": arm,
        "workspace": str(workspace.resolve()),
        "control_dir": str(private.resolve()),
        "receipt_spool": str(spool.resolve()),
        "capture_binding": binding,
        "python": sys.executable,
        "script": str((ROOT / "benchmarks" / "cursor_isolated_stop.py").resolve()),
        "isolated_supervisor": arm == "cursor_pex",
        "public_test_sha256": None,
        "decision_timeout": 40.0,
    }
    control_path = search / f"{workspace.name}.json"
    control_path.write_text(json.dumps(control), encoding="utf-8")
    return workspace, control_path, private, spool, global_drop, control


def _receipts(spool: Path) -> list[dict]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in spool.glob("*.json")]


@pytest.mark.parametrize("arm", ["cursor", "cursor_pex"])
def test_schema2_prompt_release_uses_controller_binding_and_exact_prompt_hash(
    tmp_path, monkeypatch, arm
):
    workspace, _control_path, _private, spool, global_drop, control = _schema2_control(
        tmp_path, monkeypatch, arm
    )
    hook = _load_hook(f"cursor_capture_prompt_{arm}")
    prompt = "Exact submitted prompt\nwith private details: do not persist this text."
    forged = {
        "capture_binding": {"run_id": "forged"},
        "capture_nonce": "f" * 32,
        "prompt_sha256": "f" * 64,
        "submitted_prompt_sha256": "f" * 64,
        "receipt_sha256": "forged",
        "stop_id": "../forged",
    }

    receipt_id = hook.record_prompt_release(
        {
            "hook_event_name": "beforeSubmitPrompt",
            "cwd": str(workspace),
            "conversation_id": "conversation-1",
            "generation_id": "generation-1",
            "prompt": prompt,
            **forged,
        },
        '{"continue":true}',
    )

    assert receipt_id
    assert not global_drop.exists()
    receipts = _receipts(spool)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["kind"] == "prompt_release"
    assert receipt["capture_binding"] == control["capture_binding"]
    assert receipt["capture_binding"]["capture_nonce"] == "b" * 32
    assert receipt["submitted_prompt_sha256"] == hashlib.sha256(prompt.encode()).hexdigest()
    assert receipt["submission_evidence"] == "hook_stdout_flushed"
    assert receipt["conversation_id"] == "conversation-1"
    assert receipt["generation_id"] == "generation-1"
    encoded = json.dumps(receipt)
    assert prompt not in encoded
    assert "forged" not in encoded


@pytest.mark.parametrize(
    ("bridge_body", "flush_fails", "expected_receipts"),
    [
        ('{"continue":true}', False, 1),
        ('{"continue":false,"user_message":"held"}', False, 0),
        ('{"continue":true}', True, 0),
    ],
)
def test_main_records_prompt_release_only_after_successful_continue_flush(
    tmp_path, monkeypatch, bridge_body, flush_fails, expected_receipts
):
    workspace, _control_path, _private, spool, _global_drop, _control = _schema2_control(
        tmp_path, monkeypatch, "cursor"
    )
    hook = _load_hook("cursor_capture_prompt_flush")
    payload = {
        "hook_event_name": "beforeSubmitPrompt",
        "cwd": str(workspace),
        "conversation_id": "conversation-2",
        "generation_id": "generation-2",
        "prompt": "submit this exact prompt",
    }
    monkeypatch.setattr(
        hook.sys,
        "stdin",
        SimpleNamespace(buffer=io.BytesIO(json.dumps(payload).encode("utf-8"))),
    )
    events: list[str] = []

    class Output(io.StringIO):
        def flush(self):
            events.append("flush")
            if flush_fails:
                raise OSError("stdout flush failed")
            super().flush()

    output = Output()
    monkeypatch.setattr(hook.sys, "stdout", output)
    monkeypatch.setattr(hook, "_request", lambda _payload: object())
    monkeypatch.setattr(hook, "_post", lambda *_args: bridge_body)
    original = hook.record_prompt_release

    def record(payload, stdout):
        assert events == ["flush"]
        events.append("receipt-attempt")
        return original(payload, stdout)

    monkeypatch.setattr(hook, "record_prompt_release", record)
    if flush_fails:
        with pytest.raises(OSError, match="stdout flush failed"):
            hook.main()
    else:
        hook.main()

    assert len(_receipts(spool)) == expected_receipts
    if flush_fails:
        assert events == ["flush"]
    else:
        assert events == ["flush", "receipt-attempt"]


def test_prompt_release_rejects_denial_missing_prompt_malformed_and_legacy_controls(
    tmp_path, monkeypatch
):
    workspace, control_path, _private, spool, global_drop, control = _schema2_control(
        tmp_path, monkeypatch, "cursor"
    )
    hook = _load_hook("cursor_capture_prompt_rejections")
    base = {"hook_event_name": "beforeSubmitPrompt", "cwd": str(workspace)}

    assert hook.record_prompt_release({**base, "prompt": "held"}, '{"continue":false}') is None
    assert hook.record_prompt_release(base, '{"continue":true}') is None

    malformed = dict(control)
    malformed["capture_binding"] = {**control["capture_binding"], "capture_nonce": "bad"}
    control_path.write_text(json.dumps(malformed), encoding="utf-8")
    assert (
        hook.record_prompt_release({**base, "prompt": "not captured"}, '{"continue":true}') is None
    )

    legacy = dict(control)
    legacy["schema_version"] = 1
    legacy.pop("capture_binding")
    legacy.pop("receipt_spool")
    control_path.write_text(json.dumps(legacy), encoding="utf-8")
    assert hook.record_prompt_release({**base, "prompt": "legacy"}, '{"continue":true}') is None
    assert _receipts(spool) == []
    assert not global_drop.exists()


@pytest.mark.parametrize("arm", ["cursor", "cursor_pex"])
def test_generic_activity_receipt_exports_identity_but_no_prompt_or_private_input(
    tmp_path, monkeypatch, arm
):
    workspace, _control_path, _private, spool, global_drop, control = _schema2_control(
        tmp_path, monkeypatch, arm
    )
    hook = _load_hook(f"cursor_capture_activity_{arm}")
    private = "PRIVATE-CONTENT-MUST-NOT-BE-EXPORTED"

    hook.record_hook_activity(
        {
            "hook_event_name": "afterAgentResponse",
            "cwd": str(workspace),
            "conversation_id": "conversation-3",
            "generation_id": "generation-3",
            "prompt": private,
            "input": private,
            "private_input": private,
            "tool_input": {"prompt": private},
            "text": private,
            "message": private,
            "completion": private,
            "last_assistant_message": private,
        }
    )

    assert not global_drop.exists()
    receipts = _receipts(spool)
    assert len(receipts) == 1
    receipt = receipts[0]
    assert receipt["kind"] == "hook_activity"
    assert receipt["capture_binding"] == control["capture_binding"]
    assert receipt["conversation_id"] == "conversation-3"
    assert receipt["generation_id"] == "generation-3"
    for field in (
        "prompt",
        "input",
        "private_input",
        "tool_input",
        "text",
        "message",
        "completion",
        "last_assistant_message",
    ):
        assert field not in receipt
    assert private not in json.dumps(receipt)


@pytest.mark.parametrize("arm", ["cursor", "cursor_pex"])
def test_stop_and_flushed_delivery_share_controller_binding_and_private_spool(
    tmp_path, monkeypatch, arm
):
    workspace, _control_path, _private, spool, global_drop, control = _schema2_control(
        tmp_path, monkeypatch, arm
    )
    hook = _load_hook(f"cursor_capture_stop_delivery_{arm}")
    payload = {
        "hook_event_name": "stop",
        "cwd": str(workspace),
        "conversation_id": "conversation-4",
        "generation_id": "generation-4",
        "completion": "public completion",
    }

    stop_id = hook.record_stop_drop(payload)
    delivery_id = hook.record_stop_delivery(
        payload,
        '{"followup_message":"Check the observed failing public test."}',
        stop_id,
    )

    assert stop_id and delivery_id
    assert not global_drop.exists()
    receipts = {row["kind"]: row for row in _receipts(spool)}
    assert set(receipts) == {"stop", "followup_delivery"}
    stop = receipts["stop"]
    delivery = receipts["followup_delivery"]
    assert stop["capture_binding"] == delivery["capture_binding"] == control["capture_binding"]
    assert delivery["initial_stop_id"] == stop["stop_id"]
    assert delivery["initial_receipt_sha256"] == stop["receipt_sha256"]
    assert stop["conversation_id"] == delivery["conversation_id"] == "conversation-4"
    assert stop["generation_id"] == delivery["generation_id"] == "generation-4"


def test_delivery_rejects_control_rebinding_between_stop_and_flush(tmp_path, monkeypatch):
    workspace, control_path, _private, spool, global_drop, control = _schema2_control(
        tmp_path, monkeypatch, "cursor_pex"
    )
    hook = _load_hook("cursor_capture_rebind")
    payload = {
        "hook_event_name": "stop",
        "cwd": str(workspace),
        "conversation_id": "conversation-5",
        "generation_id": "generation-5",
        "completion": "done",
    }
    stop_id = hook.record_stop_drop(payload)
    assert stop_id

    rebound_root = tmp_path / "private" / "rebound"
    rebound_spool = rebound_root / "receipts"
    rebound_spool.mkdir(parents=True)
    rebound = dict(control)
    rebound["control_dir"] = str(rebound_root.resolve())
    rebound["receipt_spool"] = str(rebound_spool.resolve())
    rebound["capture_binding"] = {
        **control["capture_binding"],
        "run_id": "different-run",
        "capture_nonce": "c" * 32,
    }
    control_path.write_text(json.dumps(rebound), encoding="utf-8")

    assert (
        hook.record_stop_delivery(
            payload,
            '{"followup_message":"Check the observed failing public test."}',
            stop_id,
        )
        is None
    )
    assert len(_receipts(spool)) == 1
    assert _receipts(rebound_spool) == []
    assert not global_drop.exists()


@pytest.mark.parametrize("arm", ["cursor", "cursor_pex"])
@pytest.mark.parametrize("hook_name", ["beforeSubmitPrompt", "afterAgentResponse"])
def test_schema2_callbacks_never_target_the_unrelated_live_bridge(
    tmp_path, monkeypatch, arm, hook_name
):
    workspace, _control_path, _private, _spool, _global_drop, _control = _schema2_control(
        tmp_path, monkeypatch, arm
    )
    hook = _load_hook(f"cursor_capture_no_bridge_{arm}_{hook_name}")

    def forbidden_endpoint():
        raise AssertionError("schema-2 benchmark callback reached the global bridge")

    monkeypatch.setattr(hook, "_endpoint", forbidden_endpoint)
    payload = {
        "hook_event_name": hook_name,
        "cwd": str(workspace),
        "conversation_id": "conversation-private",
        "generation_id": "generation-private",
        "prompt": "private prompt",
        "text": "private activity text",
    }

    assert hook._request(payload) is None


@pytest.mark.parametrize("kind", ["prompt_release", "hook_activity"])
def test_schema2_nonstop_receipt_rejects_control_loss_between_validation_and_write(
    tmp_path, monkeypatch, kind
):
    workspace, _control_path, _private, spool, global_drop, _control = _schema2_control(
        tmp_path, monkeypatch, "cursor"
    )
    hook = _load_hook(f"cursor_capture_nonstop_race_{kind}")
    original_load = hook._load_isolated_control
    calls = 0

    def disappearing_control(payload):
        nonlocal calls
        calls += 1
        return original_load(payload) if calls == 1 else None

    monkeypatch.setattr(hook, "_load_isolated_control", disappearing_control)
    payload = {
        "hook_event_name": (
            "beforeSubmitPrompt" if kind == "prompt_release" else "afterAgentResponse"
        ),
        "cwd": str(workspace),
        "conversation_id": "conversation-race",
        "generation_id": "generation-race",
        "prompt": "private prompt",
        "text": "private response",
    }

    if kind == "prompt_release":
        assert hook.record_prompt_release(payload, '{"continue":true}') is None
    else:
        hook.record_hook_activity(payload)

    assert calls == 2
    assert _receipts(spool) == []
    assert not global_drop.exists()
