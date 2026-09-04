from datetime import UTC, datetime

from pex_bridge.ask import answer_question
from pex_protocol.actions import InterventionType, ProposedAction, RiskLevel
from pex_protocol.context import ContextItem
from pex_protocol.enums import (
    Authority,
    ContextKind,
    EventType,
    HarnessType,
    PolicyVerdict,
    Sensitivity,
    SessionStatus,
    SourceKind,
)
from pex_protocol.goal import Goal
from pex_protocol.intervention import Intervention
from pex_protocol.session import HarnessSession


def _working() -> list[HarnessSession]:
    return [
        HarnessSession(
            id="cursor:1",
            harness_type=HarnessType.CURSOR,
            vendor_session_id="1",
            status=SessionStatus.WORKING,
        )
    ]


def test_ask_pex_does_not_need_worker_without_model():
    assert "Nothing needs you" in answer_question("what needs me?", _working(), [])


def test_ask_uses_supervisor_review_when_model_present(monkeypatch):
    def fake(_system: str, _user: str):
        return ("Mesh is reviewing one working session. Nothing needs you.", {}, "review_answer")

    monkeypatch.setattr("pex_supervisor.inspect_http.complete_review_answer", fake)
    answer = answer_question("give a short briefing", _working(), [], model=object())
    assert "Mesh is reviewing" in answer


def test_ask_rejects_inspect_shaped_review(monkeypatch):
    def fake(_system: str, _user: str):
        raise ValueError("inspect-shaped review payload")

    monkeypatch.setattr("pex_supervisor.inspect_http.complete_review_answer", fake)
    assert "sessions" in answer_question(
        "give a short briefing", _working(), [], model=object()
    )


def test_ask_falls_back_when_supervisor_review_fails(monkeypatch):
    def boom(_system: str, _user: str):
        raise RuntimeError("inspect unavailable")

    monkeypatch.setattr("pex_supervisor.inspect_http.complete_review_answer", boom)
    assert "sessions" in answer_question(
        "give a short briefing", _working(), [], model=object()
    )


def test_ask_minimizes_and_redacts_cloud_review_context(monkeypatch):
    captured: dict[str, str] = {}

    def fake(system: str, user: str):
        captured.update(system=system, user=user)
        return ("Safe canonical answer.", {}, "review_answer")

    monkeypatch.setattr("pex_supervisor.inspect_http.complete_review_answer", fake)
    now = datetime.now(UTC)
    sessions = _working()
    sessions[0].vendor_session_id = "PRIVATE-VENDOR-SESSION-123"
    sessions[0].goal_id = "goal-private"
    goal = Goal(
        id="goal-private",
        project_id="private-project",
        title="PRIVATE-GOAL-TITLE",
        objective="Use sk-abcdefghijklmnopqrstuvwxyz123456 safely",
        created_at=now,
        updated_at=now,
    )
    answer = answer_question(
        "Give a short briefing. token=abcdefghijklmnopqrstuvwxyz1234567890",
        sessions,
        [],
        [goal],
        model=object(),
    )
    assert answer == "Safe canonical answer."
    assert "untrusted data" in captured["system"]
    assert "instructions embedded inside" in captured["system"]
    assert "PRIVATE-VENDOR-SESSION-123" not in captured["user"]
    assert "PRIVATE-GOAL-TITLE" not in captured["user"]
    assert "abcdefghijklmnopqrstuvwxyz1234567890" not in captured["user"]
    assert "[REDACTED:" in captured["user"]


def _session(
    harness: HarnessType,
    *,
    status: SessionStatus = SessionStatus.WORKING,
    vendor: str = "1",
    goal_id: str | None = None,
    project_id: str = "demo",
    cwd: str | None = None,
) -> HarnessSession:
    return HarnessSession(
        id=f"{harness.value}:{vendor}",
        harness_type=harness,
        vendor_session_id=vendor,
        status=status,
        project_id=project_id,
        goal_id=goal_id,
        cwd=cwd,
        last_activity=datetime.now(UTC),
    )


def _nudge(session_id: str, diagnosis: str, *, verification: dict | None = None) -> Intervention:
    action = ProposedAction(
        type=InterventionType.SEND_NUDGE,
        session_id=session_id,
        payload={"text": diagnosis},
        rationale=diagnosis,
        evidence=["observed:canonical"],
        risk=RiskLevel.LOW,
        authority_required=Authority.LOCAL_POLICY,
    )
    return Intervention(
        id=f"int-{session_id}",
        session_id=session_id,
        trigger=EventType.STOP.value,
        evidence=list(action.evidence),
        diagnosis=diagnosis,
        proposed_action=action,
        risk=action.risk.value,
        authority_required=action.authority_required.value,
        action_taken=action.type.value,
        policy_verdict=PolicyVerdict.ALLOW,
        result="sent",
        created_at=datetime.now(UTC),
        metadata={"verification": verification or {}},
    )


def _fact(item_id: str, content: str, source_session_id: str) -> ContextItem:
    now = datetime.now(UTC)
    return ContextItem(
        id=item_id,
        project_id="demo",
        goal_id="goal-parser",
        kind=ContextKind.FACT,
        content=content,
        source_refs=[f"event:{item_id}"],
        provenance=SourceKind.HARNESS,
        confidence=0.9,
        relevance_tags=["parser"],
        valid_from=now,
        sensitivity=Sensitivity.INTERNAL,
        metadata={"source_session_id": source_session_id},
    )


def test_ask_answers_what_codex_is_doing_from_session_state():
    goal = Goal(
        id="goal-parser",
        project_id="demo",
        title="Parser",
        objective="Implement the parser",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    answer = answer_question(
        "what is Codex doing?",
        [_session(HarnessType.CODEX, goal_id="goal-parser")],
        [],
        [goal],
    )
    assert "codex is working" in answer.lower()
    assert "Parser" in answer


def test_ask_spec_answers_are_not_overridden_by_supervisor_model(monkeypatch):
    def fake(_system: str, _user: str):
        raise AssertionError("canonical Ask answers must not call supervisor review")

    monkeypatch.setattr("pex_supervisor.inspect_http.complete_review_answer", fake)
    sessions = [_session(HarnessType.CODEX, goal_id="goal-parser")]
    answer = answer_question("what is Codex doing?", sessions, [], model=object())
    assert "codex is working" in answer.lower()
    assert "Nothing needs you" in answer_question(
        "what needs me?", _working(), [], model=object()
    )


def test_ask_does_not_invent_a_missing_codex_session():
    answer = answer_question("what is Codex doing?", _working(), [])
    assert "no codex session is attached" in answer.lower()


def test_ask_names_the_blocked_agent():
    sessions = [
        _session(HarnessType.CURSOR),
        _session(HarnessType.DEVIN, status=SessionStatus.BLOCKED, vendor="blocked"),
    ]
    answer = answer_question("which agent is blocked?", sessions, [])
    assert "devin" in answer.lower()
    assert "blocked" in answer.lower()


def test_ask_explains_why_it_messaged_cursor_from_that_session():
    cursor = _nudge("cursor:1", "Cursor drifted off the attached ledger.")
    later = _nudge("codex:1", "Codex is still working.")
    later.id = "int-later"
    answer = answer_question(
        "why did you message Cursor?",
        [_session(HarnessType.CURSOR), _session(HarnessType.CODEX)],
        [later, cursor],
    )
    assert "Cursor drifted off the attached ledger." in answer
    assert "SEND_NUDGE" in answer


def test_ask_reports_devin_context_codex_does_not_have():
    sessions = [_session(HarnessType.DEVIN), _session(HarnessType.CODEX)]
    answer = answer_question(
        "what does Devin know that Codex doesn't?",
        sessions,
        [],
        context=[_fact("ctx-devin", "The schema freeze is already signed.", "devin:1")],
    )
    assert "schema freeze is already signed" in answer
    assert "codex does not have that item" in answer.lower()


def test_ask_does_not_leak_secret_context_in_knowledge_gap():
    sessions = [_session(HarnessType.DEVIN), _session(HarnessType.CODEX)]
    secret = _fact("ctx-secret", "prod token is sk-secret", "devin:1")
    secret.sensitivity = Sensitivity.SECRET
    answer = answer_question(
        "what does Devin know that Codex doesn't?",
        sessions,
        [],
        context=[secret],
    )
    assert "sk-secret" not in answer
    assert "does not show anything" in answer.lower()


def test_ask_will_not_guess_which_approach_looks_better():
    answer = answer_question("which approach looks better?", _working(), [])
    assert "will not guess" in answer.lower()


def test_ask_reports_eval_completion_from_observed_verification():
    intervention = _nudge(
        "codex:1",
        "Stop observed.",
        verification={"status": "supported"},
    )
    answer = answer_question(
        "did the eval actually finish?",
        [_session(HarnessType.CODEX)],
        [intervention],
    )
    assert "supports completion" in answer.lower()


def test_ask_does_not_claim_eval_finished_without_evidence():
    answer = answer_question("did the eval actually finish?", _working(), [])
    assert "has not observed evaluation evidence" in answer.lower()


def test_ask_inspects_eval_artifact_rows_without_interrupting(tmp_path):
    (tmp_path / "results.jsonl").write_text(
        '{"id":1}\n{"id":2}\n{"id":3}\n',
        encoding="utf-8",
    )
    goal = Goal(
        id="goal-eval",
        project_id="demo",
        title="Eval",
        objective="Run the evaluation",
        acceptance_criteria=["30 evaluation rows"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = _session(HarnessType.CODEX, goal_id="goal-eval", cwd=str(tmp_path))
    answer = answer_question("did the eval actually finish?", [session], [], [goal])
    assert "no." in answer.lower()
    assert "3 rows" in answer
    assert "30" in answer
    assert "inspected results.jsonl" in answer.lower()


def test_ask_reports_matching_eval_artifact_without_calling_it_a_stop_verification(tmp_path):
    rows = "\n".join(f'{{"id":{index}}}' for index in range(30)) + "\n"
    (tmp_path / "results.jsonl").write_text(rows, encoding="utf-8")
    goal = Goal(
        id="goal-eval",
        project_id="demo",
        title="Eval",
        objective="Run the evaluation",
        acceptance_criteria=["30 evaluation rows"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session = _session(HarnessType.CODEX, goal_id="goal-eval", cwd=str(tmp_path))
    answer = answer_question("did the eval actually finish?", [session], [], [goal])
    assert "30 rows" in answer
    assert "workspace evidence" in answer.lower()
    assert "supports completion" not in answer.lower()
