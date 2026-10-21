"""Synthetic schema/unit tests only: never provider access or a benchmark."""

import copy
import json
from time import monotonic

import pytest

from benchmarks import opencode_native as native


def events():
    base = {"sessionID": "ses_test", "messageID": "msg_test"}
    return [
        {
            "type": "step_start",
            "timestamp": 1,
            "sessionID": "ses_test",
            "part": {**base, "id": "prt_start", "type": "step-start"},
        },
        {
            "type": "text",
            "timestamp": 2,
            "sessionID": "ses_test",
            "part": {
                **base,
                "id": "prt_text",
                "type": "text",
                "text": "Done",
                "time": {"start": 1, "end": 2},
            },
        },
        {
            "type": "step_finish",
            "timestamp": 3,
            "sessionID": "ses_test",
            "part": {
                **base,
                "id": "prt_finish",
                "type": "step-finish",
                "reason": "stop",
                "cost": 0,
                "tokens": {
                    "input": 2,
                    "output": 3,
                    "reasoning": 1,
                    "cache": {"read": 0, "write": 0},
                },
            },
        },
    ]


def encode(rows):
    return b"\n".join(json.dumps(x).encode() for x in rows)


def test_native_observation_preserves_usage_without_inventing_total():
    result = native.parse_native_turn(encode(events()), exit_code=0)
    assert result.provenance == "native_cli_worker_reported_not_provider_wire"
    assert result.provider_model_verified is False
    assert result.quality_measured is False
    assert "total" not in result.steps[0]["tokens"]
    assert result.steps[0]["tokens"]["reasoning"] == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e[-1]["part"]["tokens"].pop("input"),
        lambda e: e[-1]["part"]["tokens"].update(total_tokens=6),
        lambda e: e[-1]["part"]["tokens"].update(input=True),
        lambda e: e[-1]["part"]["tokens"].update(input=float("nan")),
        lambda e: e[-1]["part"]["tokens"]["cache"].update(read=-1),
        lambda e: e[-1]["part"].update(reason="length"),
        lambda e: e[-1]["part"].update(reason=[]),
        lambda e: e[-1]["part"].update(type="text"),
        lambda e: e[-1].update(providerID="opencode"),
        lambda e: e[1].update(type="unknown"),
        lambda e: e[1].update(type="error"),
        lambda e: e[1]["part"].update(id="prt_start"),
        lambda e: e[1]["part"].update(sessionID="ses_other"),
        lambda e: e[1]["part"].update(messageID="msg_other"),
        lambda e: e[1]["part"]["time"].update(end=0),
        lambda e: e.pop(0),
        lambda e: e.pop(),
        lambda e: e.append(copy.deepcopy(e[0])),
    ],
)
def test_native_parser_rejects_unknown_or_unproven_events(mutate):
    rows = events()
    mutate(rows)
    with pytest.raises(ValueError):
        native.parse_native_turn(encode(rows), exit_code=0)


def test_native_duplicate_json_key_and_failed_process_rejected():
    raw = encode(events())
    with pytest.raises(ValueError):
        native.parse_native_turn(
            raw.replace(b'"timestamp": 1', b'"timestamp": 1,"timestamp": 1'), exit_code=0
        )
    with pytest.raises(ValueError):
        native.parse_native_turn(raw, exit_code=1)
    with pytest.raises(ValueError):
        native.parse_native_turn(raw, exit_code=0, expected_session="ses_other")


def test_tool_cycle_is_supported_and_usage_is_step_scoped():
    rows = events()
    rows[-1]["part"]["reason"] = "tool-calls"
    tool = {
        "type": "tool_use",
        "timestamp": 2,
        "sessionID": "ses_test",
        "part": {
            "id": "prt_tool",
            "sessionID": "ses_test",
            "messageID": "msg_test",
            "type": "tool",
            "callID": "call1",
            "tool": "bash",
            "state": {
                "status": "completed",
                "input": {},
                "output": "ok",
                "title": "test",
                "metadata": {},
                "time": {"start": 1, "end": 2},
            },
        },
    }
    rows.insert(2, tool)
    other = events()
    for row in other:
        row["part"]["messageID"] = "msg_next"
        row["part"]["id"] += "next"
    result = native.parse_native_turn(encode(rows + other), exit_code=0)
    assert len(result.steps) == 2


def test_settings_never_relay_or_fallback():
    config = native.native_settings(version=native.VERSION, model=native.MODEL, steps=10)
    assert "provider" not in config
    assert config["model"] == config["small_model"] == native.MODEL
    assert config["enabled_providers"] == ["opencode"]
    assert config["permission"]["external_directory"] == "deny"
    for version, model in [
        ("2.1.2", native.MODEL),
        (native.VERSION, "controlled/foo"),
        (native.VERSION, "opencode/deepseek-v4.1"),
    ]:
        with pytest.raises(ValueError):
            native.native_settings(version=version, model=model, steps=10)


def test_native_controller_admission_remains_closed():
    with pytest.raises(RuntimeError, match="audited native egress isolation"):
        native.admit_native_attempt()


@pytest.mark.asyncio
async def test_native_same_session_deadline_and_review_use_strict_receipts(tmp_path, monkeypatch):
    binary = tmp_path / "opencode"
    binary.write_bytes(b"synthetic-not-an-executable")
    monkeypatch.setattr(
        native, "BINARY_SHA256", native.hashlib.sha256(binary.read_bytes()).hexdigest()
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls, reviews = [], []
    deadline = monotonic() + 30

    async def fake_turn(**kwargs):
        calls.append(kwargs)
        rows = events()
        for row in rows:
            row["part"]["messageID"] += str(len(calls))
            row["part"]["id"] += str(len(calls))
        raw = encode(rows)
        kwargs["stdout_path"].write_bytes(raw)
        return native.completed_turn(raw, exit_code=0, expected_session=kwargs["session_id"])

    async def review(receipts):
        reviews.append(receipts)
        return (
            {"type": "SEND_NUDGE", "payload": {"text": "Verify"}}
            if len(receipts) == 1
            else {"type": "NOOP"}
        )

    monkeypatch.setattr(native, "run_turn", fake_turn)
    result, receipts = await native.run_native_session(
        executable=binary,
        workspace=workspace,
        state_home=tmp_path / "state",
        log_directory=tmp_path / "logs",
        prompt="Task",
        deadline=deadline,
        version=native.VERSION,
        model=native.MODEL,
        steps=10,
        max_followups=1,
        review=review,
    )
    assert len(receipts) == 2
    assert result.outgoing_messages == ("Verify",)
    assert calls[0]["session_id"] is None
    assert calls[1]["session_id"] == "ses_test"
    assert all(c["deadline"] == deadline and c["model"] == native.MODEL for c in calls)
    assert all(r[-1].provenance == native.PROVENANCE for r in reviews)
    assert "API_KEY" not in json.dumps(calls[0]["environment"])
    assert calls[0]["environment"] == calls[1]["environment"]


@pytest.mark.asyncio
async def test_wrong_binary_never_launches(tmp_path, monkeypatch):
    binary = tmp_path / "opencode"
    binary.write_bytes(b"wrong")

    async def forbidden(**kwargs):
        pytest.fail("must not launch")

    monkeypatch.setattr(native, "run_turn", forbidden)
    with pytest.raises(ValueError, match="binary digest"):
        await native.run_native_session(
            executable=binary,
            workspace=tmp_path / "workspace",
            state_home=tmp_path / "state",
            log_directory=tmp_path / "logs",
            prompt="Task",
            deadline=monotonic() + 30,
            version=native.VERSION,
            model=native.MODEL,
            steps=10,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["replayed_message", "replayed_part", "changed_binary"])
async def test_followup_rejects_replay_or_runtime_drift(tmp_path, monkeypatch, defect):
    binary = tmp_path / "opencode"
    binary.write_bytes(b"synthetic-not-an-executable")
    monkeypatch.setattr(native, "BINARY_SHA256", native.hashlib.sha256(binary.read_bytes()).hexdigest())
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    calls = []

    async def fake_turn(**kwargs):
        calls.append(kwargs)
        rows = events()
        if len(calls) > 1:
            for row in rows:
                if defect != "replayed_message": row["part"]["messageID"] += "new"
                if defect != "replayed_part": row["part"]["id"] += "new"
        raw = encode(rows)
        kwargs["stdout_path"].write_bytes(raw)
        return native.completed_turn(raw, exit_code=0, expected_session=kwargs["session_id"])

    async def review(receipts):
        if defect == "changed_binary": binary.write_bytes(b"changed")
        return {"type": "SEND_NUDGE", "payload": {"text": "Verify"}}

    monkeypatch.setattr(native, "run_turn", fake_turn)
    with pytest.raises(ValueError, match="replayed|binary digest"):
        await native.run_native_session(
            executable=binary, workspace=workspace, state_home=tmp_path / "state",
            log_directory=tmp_path / "logs", prompt="Task", deadline=monotonic() + 30,
            version=native.VERSION, model=native.MODEL, steps=10,
            max_followups=1, review=review,
        )
    assert len(calls) == (1 if defect == "changed_binary" else 2)


@pytest.mark.asyncio
async def test_binary_inside_writable_task_is_rejected_before_launch(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    binary = workspace / "opencode"
    binary.write_bytes(b"synthetic-not-an-executable")
    monkeypatch.setattr(native, "BINARY_SHA256", native.hashlib.sha256(binary.read_bytes()).hexdigest())
    async def forbidden(**kwargs):
        pytest.fail("must not launch")
    monkeypatch.setattr(native, "run_turn", forbidden)
    with pytest.raises(ValueError, match="outside task"):
        await native.run_native_session(
            executable=binary, workspace=workspace, state_home=tmp_path / "state",
            log_directory=tmp_path / "logs", prompt="Task", deadline=monotonic() + 30,
            version=native.VERSION, model=native.MODEL, steps=10,
        )
