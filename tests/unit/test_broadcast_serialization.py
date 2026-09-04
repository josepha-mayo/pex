from __future__ import annotations

import asyncio

import pytest
from pex_bridge.app import AppState


class _Concurrency:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0


class _Socket:
    def __init__(self, shared: _Concurrency | None = None, *, fail: bool = False) -> None:
        self.shared = shared or _Concurrency()
        self.fail = fail
        self.messages: list[dict] = []
        self.closed: tuple[int, str] | None = None

    async def send_json(self, message: dict) -> None:
        self.shared.active += 1
        self.shared.max_active = max(self.shared.max_active, self.shared.active)
        try:
            await asyncio.sleep(0.02)
            if self.fail:
                raise RuntimeError("disconnected")
            self.messages.append(message)
        finally:
            self.shared.active -= 1

    async def close(self, *, code: int, reason: str) -> None:
        self.closed = (code, reason)


@pytest.mark.asyncio
async def test_concurrent_broadcasts_never_write_one_websocket_concurrently():
    state = AppState()
    socket = _Socket()
    state.sockets.append(socket)  # type: ignore[arg-type]

    await asyncio.gather(
        state.broadcast("intervention", {"sequence": 1}),
        state.broadcast("intervention", {"sequence": 2}),
    )

    assert socket.shared.max_active == 1
    assert len(socket.messages) == 2


@pytest.mark.asyncio
async def test_broadcasts_to_independent_websockets_remain_parallel():
    state = AppState()
    shared = _Concurrency()
    first = _Socket(shared)
    second = _Socket(shared)
    state.sockets.extend([first, second])  # type: ignore[list-item]

    await state.broadcast("intervention", {"sequence": 1})

    assert shared.max_active == 2
    assert len(first.messages) == len(second.messages) == 1


@pytest.mark.asyncio
async def test_failed_websocket_is_removed_from_future_broadcasts():
    state = AppState()
    dead = _Socket(fail=True)
    state.sockets.append(dead)  # type: ignore[arg-type]

    await state.broadcast("intervention", {"sequence": 1})

    assert dead not in state.sockets
    assert dead not in state._socket_send_locks


@pytest.mark.asyncio
async def test_event_broadcast_is_only_a_wake_hint_not_a_delivery_path():
    state = AppState()
    socket = _Socket()
    state.sockets.append(socket)  # type: ignore[arg-type]

    await state.broadcast("event", {"event_id": "evt-not-authoritative"})

    assert socket.messages == []


@pytest.mark.asyncio
async def test_full_socket_queue_closes_and_unregisters_slow_consumer():
    state = AppState()
    socket = _Socket()
    queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1)
    queue.put_nowait({"topic": "existing", "payload": {}})
    state.sockets.append(socket)  # type: ignore[arg-type]
    state._socket_queues[socket] = queue  # type: ignore[index]

    await state.broadcast("intervention", {"sequence": 2})

    assert socket.closed == (1013, "event socket queue full")
    assert socket not in state.sockets
    assert socket not in state._socket_queues
