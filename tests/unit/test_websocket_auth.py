import asyncio
import base64
import threading

from fastapi.testclient import TestClient
from pex_bridge.app import create_app, state
from pex_bridge.config import Settings
from starlette.websockets import WebSocketDisconnect


def test_websocket_requires_token_even_for_tauri_origin(tmp_path, monkeypatch):
    state.settings = Settings(require_auth=True, home=tmp_path, codex_attach=False)
    state.token = f"{'x' * 31},"
    state.sockets.clear()
    state._socket_queues.clear()

    async def live_pet():
        return {"headline": "authenticated"}

    async def empty_event_page(**_kwargs):
        return {
            "through": "0",
            "next": "0",
            "items": [],
            "has_more": False,
            "gap": {"detected": False},
        }

    monkeypatch.setattr(state, "live_pet", live_pet)
    monkeypatch.setattr(state.store, "event_publication_page", empty_event_page)
    client = TestClient(create_app(), base_url="http://127.0.0.1")

    try:
        with client.websocket_connect(
            "/v1/events?token=local-test-token",
            headers={"origin": "tauri://localhost", "host": "127.0.0.1"},
        ):
            raise AssertionError("tokens in loggable query strings must be rejected")
    except WebSocketDisconnect as exc:
        assert exc.code == 1008

    try:
        with client.websocket_connect(
            "/v1/events",
            headers={"origin": "tauri://localhost", "host": "127.0.0.1"},
            subprotocols=["pex-v1", "wrong-token"],
        ):
            raise AssertionError("an invalid token must not open the event stream")
    except WebSocketDisconnect as exc:
        assert exc.code == 1008

    try:
        with client.websocket_connect(
            "/v1/events",
            headers={"origin": "tauri://localhost", "host": "127.0.0.1"},
            subprotocols=["pex-v1", state.token],
        ):
            raise AssertionError("the raw bearer must not be used as a subprotocol")
    except WebSocketDisconnect as exc:
        assert exc.code == 1008

    encoded = base64.urlsafe_b64encode(state.token.encode("ascii")).decode("ascii").rstrip("=")

    with client.websocket_connect(
        "/v1/events",
        headers={"origin": "tauri://localhost", "host": "127.0.0.1"},
        subprotocols=["pex-v1", f"pex-token.{encoded}"],
    ) as socket:
        assert socket.accepted_subprotocol == "pex-v1"
        assert socket.receive_json() == {
            "topic": "pet",
            "payload": {"headline": "authenticated"},
        }

    # WebSocketTestSession cancels its AnyIO scope immediately after sending
    # disconnect.  Handler cleanup must detach the socket before any awaited
    # cancellation point, so the registry is already exact when the context
    # manager returns.
    assert state.sockets == []
    assert state._socket_queues == {}
    assert state._socket_send_locks == {}
    client.close()


def test_websocket_resumes_from_decimal_cursor_via_durable_pages(tmp_path, monkeypatch):
    state.settings = Settings.for_test(
        require_auth=False,
        home=tmp_path,
        codex_attach=False,
    )
    state.sockets.clear()
    state._socket_queues.clear()
    calls = []

    async def live_pet():
        return {"headline": "resume"}

    async def event_page(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return {
                "schema": "pex.event-page.v1",
                "through": "2",
                "next": "2",
                "watermark": "2",
                "items": [
                    {
                        "cursor": "2",
                        "event": {"event_id": "evt-two"},
                    }
                ],
                "has_more": False,
                "gap": {"detected": False},
            }
        return {
            "schema": "pex.event-page.v1",
            "through": "2",
            "next": "2",
            "watermark": "2",
            "items": [],
            "has_more": False,
            "gap": {"detected": False},
        }

    monkeypatch.setattr(state, "live_pet", live_pet)
    monkeypatch.setattr(state.store, "event_publication_page", event_page)
    client = TestClient(create_app(), base_url="http://127.0.0.1")

    with client.websocket_connect(
        "/v1/events?after=1",
        headers={"origin": "tauri://localhost", "host": "127.0.0.1"},
        subprotocols=["pex-v1"],
    ) as socket:
        assert socket.receive_json()["topic"] == "pet"
        page = socket.receive_json()
        assert page["topic"] == "event_page"
        assert page["payload"]["items"][0]["cursor"] == "2"

    assert calls[0]["after"] == 1
    assert calls[0]["through"] is None

    try:
        with client.websocket_connect(
            "/v1/events?after=01",
            headers={"origin": "tauri://localhost", "host": "127.0.0.1"},
        ):
            raise AssertionError("non-canonical event cursors must be rejected")
    except WebSocketDisconnect as exc:
        assert exc.code == 1008

    client.close()
    state.sockets.clear()
    state._socket_queues.clear()


def test_websocket_cancellation_detaches_before_blocked_tail_cleanup(tmp_path, monkeypatch):
    state.settings = Settings.for_test(
        require_auth=False,
        home=tmp_path,
        codex_attach=False,
    )
    state.sockets.clear()
    state._socket_queues.clear()
    state._socket_send_locks.clear()
    tail_entered = threading.Event()

    async def live_pet():
        return {"headline": "cancellation-safe"}

    async def blocked_event_page(**_kwargs):
        tail_entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(state, "live_pet", live_pet)
    monkeypatch.setattr(state.store, "event_publication_page", blocked_event_page)
    client = TestClient(create_app(), base_url="http://127.0.0.1")

    with client.websocket_connect(
        "/v1/events",
        headers={"origin": "tauri://localhost", "host": "127.0.0.1"},
        subprotocols=["pex-v1"],
    ) as socket:
        assert socket.receive_json()["payload"]["headline"] == "cancellation-safe"
        assert tail_entered.wait(timeout=1.0)

    assert state.sockets == []
    assert state._socket_queues == {}
    assert state._socket_send_locks == {}
    client.close()
