from pex_bridge.adapters.acp_client import AcpClient, FakeAcpTransport
from pex_bridge.adapters.cursor import CursorAdapter
from pex_bridge.adapters.cursor_bin import resolve_cursor_agent
from pex_bridge.ask import answer_question
from pex_protocol.enums import HarnessType, SessionStatus
from pex_protocol.session import HarnessSession


def test_never_resolves_grok_agent(monkeypatch, tmp_path):
    grok = tmp_path / ".grok" / "bin" / "agent.exe"
    grok.parent.mkdir(parents=True)
    grok.write_text("fake")
    monkeypatch.setenv("PEX_CURSOR_AGENT", str(grok))
    resolved = resolve_cursor_agent()
    assert resolved is None or ".grok" not in resolved.lower()


def test_resolves_explicit_cursor_agent(tmp_path, monkeypatch):
    agent = tmp_path / "cursor-agent.exe"
    agent.write_text("fake")
    monkeypatch.setenv("PEX_CURSOR_AGENT", str(agent))
    assert resolve_cursor_agent() == str(agent)


async def test_acp_prompt_and_session_list():
    transport = FakeAcpTransport()
    adapter = CursorAdapter()
    adapter.attach_acp(transport)
    sessions = await adapter.discover_sessions()
    assert any(s.vendor_session_id == "cursor-acp-demo" for s in sessions)
    target = sessions[0]
    ok = await adapter.send_message(target, "PEX: continue; tests were not run.")
    assert ok
    assert transport.prompts
    assert "tests were not run" in transport.prompts[0]["prompt"][0]["text"]
    caps = await adapter.probe()
    assert caps.support_label.value == "deep"


def test_ask_pex_does_not_need_worker():
    sessions = [
        HarnessSession(
            id="cursor:1",
            harness_type=HarnessType.CURSOR,
            vendor_session_id="1",
            status=SessionStatus.WORKING,
        )
    ]
    assert "Nothing needs you" in answer_question("what needs me?", sessions, [])
