from pex_bridge.ask import answer_question
from pex_protocol.enums import HarnessType, SessionStatus
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
    answer = answer_question("what needs me?", _working(), [], model=object())
    assert "Mesh is reviewing" in answer


def test_ask_rejects_inspect_shaped_review(monkeypatch):
    def fake(_system: str, _user: str):
        raise ValueError("inspect-shaped review payload")

    monkeypatch.setattr("pex_supervisor.inspect_http.complete_review_answer", fake)
    assert "Nothing needs you" in answer_question("what needs me?", _working(), [], model=object())


def test_ask_falls_back_when_supervisor_review_fails(monkeypatch):
    def boom(_system: str, _user: str):
        raise RuntimeError("inspect unavailable")

    monkeypatch.setattr("pex_supervisor.inspect_http.complete_review_answer", boom)
    assert "Nothing needs you" in answer_question("what needs me?", _working(), [], model=object())
