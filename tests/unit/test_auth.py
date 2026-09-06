import hashlib
import hmac
import os
import stat
import subprocess
import sys

import pytest
from httpx import ASGITransport, AsyncClient
from pex_bridge.adapters import AdapterRegistry
from pex_bridge.app import (
    _atomic_write_text,
    _BridgeStateLock,
    _load_or_create_bridge_token,
    _open_token_parent,
    create_app,
    state,
)
from pex_bridge.bus import EventBus
from pex_bridge.config import Settings
from pex_bridge.pipeline import Pipeline
from pex_bridge.store import Store


def test_bridge_state_lock_rejects_a_second_process_and_releases(tmp_path):
    database_path = tmp_path / "pex.sqlite"
    lock = _BridgeStateLock(database_path)
    subprocess_timeout = 30
    script = (
        "import sys; from pathlib import Path; "
        "from pex_bridge.app import _BridgeStateLock; "
        "lock = _BridgeStateLock(Path(sys.argv[1])); "
        "lock.acquire(); lock.release()"
    )

    lock.acquire()
    try:
        blocked = subprocess.run(
            [sys.executable, "-c", script, str(database_path)],
            capture_output=True,
            text=True,
            timeout=subprocess_timeout,
            check=False,
        )
        assert blocked.returncode != 0
        assert "could not acquire the state database lock" in blocked.stderr
    finally:
        lock.release()

    acquired = subprocess.run(
        [sys.executable, "-c", script, str(database_path)],
        capture_output=True,
        text=True,
        timeout=subprocess_timeout,
        check=False,
    )
    assert acquired.returncode == 0, acquired.stderr
    lock.release()


def test_bridge_state_lock_descriptor_is_not_inherited(tmp_path):
    lock = _BridgeStateLock(tmp_path / "pex.sqlite")
    lock.acquire()
    try:
        assert lock._descriptor is not None
        assert os.get_inheritable(lock._descriptor) is False
    finally:
        lock.release()


def test_release_cli_rejects_no_auth_flag():
    completed = subprocess.run(
        [sys.executable, "-m", "pex_bridge", "--no-auth"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert completed.returncode == 2
    assert "unrecognized arguments: --no-auth" in completed.stderr


def test_release_main_scrubs_operator_token_before_worker_spawns(monkeypatch):
    import pex_bridge.adapters.cursor as cursor_module
    import pex_bridge.main as bridge_main
    import uvicorn
    from pex_bridge.adapters.cursor import _bridge_token

    operator = "desktop-owned-operator-token-that-is-long-enough"
    monkeypatch.setattr(state, "token", operator)
    monkeypatch.setattr(cursor_module, "_INTERNAL_BRIDGE_TOKEN", "")
    monkeypatch.setenv("PEX_TOKEN", operator)
    monkeypatch.setattr(sys, "argv", ["pex-bridge", "--host", "127.0.0.1", "--port", "7420"])
    launched: dict[str, object] = {}

    def fake_run(app, *, host, port, log_level):
        launched.update(app=app, host=host, port=port, log_level=log_level)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    bridge_main.main()

    assert os.environ.get("PEX_TOKEN") is None
    assert _bridge_token() == operator
    assert launched["host"] == "127.0.0.1"
    assert launched["port"] == 7420


def test_direct_asgi_import_consumes_operator_env_before_any_child_spawn(tmp_path):
    operator = "direct-asgi-operator-token-that-is-long-enough"
    environment = os.environ.copy()
    environment["PEX_TOKEN"] = operator
    environment["PEX_HOME"] = str(tmp_path)
    script = """
import os
import subprocess
import sys

operator = os.environ["PEX_TOKEN"]
from pex_bridge.adapters.cursor import _bridge_token
from pex_bridge.app import state

assert os.environ.get("PEX_TOKEN") is None
assert state.token == operator
assert state.settings.token is None
assert _bridge_token() == operator
assert operator not in repr(state.settings)
child = subprocess.run(
    [sys.executable, "-c", "import os; raise SystemExit('PEX_TOKEN' in os.environ)"],
    check=False,
)
assert child.returncode == 0
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert operator not in completed.stdout
    assert operator not in completed.stderr


def test_bridge_token_creation_is_persistent_and_owner_only(tmp_path):
    path = tmp_path / "bridge.token"
    first = _load_or_create_bridge_token(path)
    second = _load_or_create_bridge_token(path)
    assert first == second == path.read_text(encoding="utf-8")
    assert len(first) >= 32
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "nt", reason="Windows token ACL")
def test_bridge_token_windows_acl_is_owner_only_and_holds_parent(tmp_path):
    path = tmp_path / "nested" / "bridge.token"
    parent = _open_token_parent(path)
    assert parent is not None
    try:
        assert stat.S_ISDIR(os.fstat(parent).st_mode)
    finally:
        os.close(parent)
    _load_or_create_bridge_token(path)
    listing = subprocess.check_output(["icacls", str(path)], text=True)
    lowered = listing.casefold()
    assert "everyone:" not in lowered
    assert "builtin\\users:" not in lowered
    assert "\\users:" not in lowered
    username = os.environ.get("USERNAME", "")
    assert username
    assert username.casefold() in lowered


def test_empty_bridge_token_file_fails_closed(tmp_path):
    path = tmp_path / "bridge.token"
    path.write_text("", encoding="utf-8")
    with pytest.raises(RuntimeError, match="token file is empty"):
        _load_or_create_bridge_token(path)


def test_short_bridge_token_file_fails_closed(tmp_path):
    path = tmp_path / "bridge.token"
    path.write_text("guessable", encoding="utf-8")
    with pytest.raises(RuntimeError, match="32-512 printable ASCII"):
        _load_or_create_bridge_token(path)


def test_bridge_token_file_rejects_non_regular_oversized_and_invalid_utf8(tmp_path):
    path = tmp_path / "bridge.token"
    path.mkdir()
    with pytest.raises(RuntimeError, match="token file"):
        _load_or_create_bridge_token(path)

    path.rmdir()
    path.write_bytes(b"x" * 4097)
    with pytest.raises(RuntimeError, match="safety bound"):
        _load_or_create_bridge_token(path)

    path.write_bytes(b"\xff" * 32)
    with pytest.raises(RuntimeError, match="valid UTF-8"):
        _load_or_create_bridge_token(path)


def test_bridge_token_file_rejects_hard_links(tmp_path):
    path = tmp_path / "bridge.token"
    path.write_text("x" * 32, encoding="utf-8")
    os.link(path, tmp_path / "other.token")
    with pytest.raises(RuntimeError, match="exactly one link"):
        _load_or_create_bridge_token(path)


def test_bridge_token_file_rejects_links_including_dangling_links(tmp_path):
    target = tmp_path / "target.token"
    target.write_text("x" * 32, encoding="utf-8")
    path = tmp_path / "bridge.token"
    try:
        path.symlink_to(target)
    except OSError as exc:
        code = getattr(exc, "winerror", None) or exc.errno
        pytest.skip(f"file symlink creation is unavailable: {code}")
    with pytest.raises(RuntimeError, match="link or reparse point"):
        _load_or_create_bridge_token(path)

    path.unlink()
    path.symlink_to(tmp_path / "missing.token")
    with pytest.raises(RuntimeError, match="link or reparse point"):
        _load_or_create_bridge_token(path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX FIFO semantics")
def test_bridge_token_file_rejects_fifo_without_blocking(tmp_path):
    path = tmp_path / "bridge.token"
    os.mkfifo(path)
    with pytest.raises(RuntimeError, match="regular file"):
        _load_or_create_bridge_token(path)


def test_bridge_token_file_detects_identity_change_during_open(tmp_path, monkeypatch):
    path = tmp_path / "bridge.token"
    other = tmp_path / "other.token"
    path.write_text("x" * 32, encoding="utf-8")
    other.write_text("y" * 32, encoding="utf-8")
    real_stat = os.lstat
    calls = 0

    def changing_stat(candidate, parent_descriptor):
        nonlocal calls
        del parent_descriptor
        calls += 1
        return real_stat(path if calls == 1 else other)

    monkeypatch.setattr("pex_bridge.app._token_path_stat", changing_stat)
    with pytest.raises(RuntimeError, match="changed while it was opened"):
        _load_or_create_bridge_token(path)


def test_atomic_control_file_write_never_replaces_with_partial_content(tmp_path, monkeypatch):
    path = tmp_path / "pet.json"
    path.write_text('{"selected_id":"pex"}', encoding="utf-8")

    def fail_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr("pex_bridge.app.os.replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        _atomic_write_text(path, '{"selected_id":"von"}')

    assert path.read_text(encoding="utf-8") == '{"selected_id":"pex"}'
    assert list(tmp_path.glob(".*.tmp")) == []


async def test_control_api_requires_exact_bearer_token_and_fails_closed(tmp_path):
    settings = Settings(require_auth=True, home=tmp_path, codex_attach=False)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    token = "local-test-token-that-is-at-least-32"
    state.token = token
    await store.connect()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as client:
            # Public liveness is intentionally not an identity proof. The
            # desktop trusts only the separate nonce-bound HMAC response.
            assert (await client.get("/health/live")).status_code == 200
            challenge = "ab" * 32
            identity = await client.get(
                "/health/identity",
                params={"challenge": challenge},
            )
            assert identity.status_code == 200
            assert identity.json() == {
                "ok": True,
                "service": "pex-bridge",
                "challenge": challenge,
                "proof": hmac.new(
                    token.encode("ascii"),
                    challenge.encode("ascii"),
                    hashlib.sha256,
                ).hexdigest(),
            }
            assert (
                await client.get("/health/identity", params={"challenge": "not-hex"})
            ).status_code == 422
            assert (await client.get("/health")).status_code == 401
            assert (await client.get("/v1/goals")).status_code == 401
            assert (await client.get("/v1/channels")).status_code == 401
            assert (
                await client.get(
                    "/v1/goals",
                    headers={"Authorization": f"Token {token}"},
                )
            ).status_code == 401
            assert (
                await client.get(
                    "/v1/goals",
                    headers={"Authorization": "Bearer wrong-token"},
                )
            ).status_code == 401
            assert (
                await client.get(
                    "/v1/goals",
                    headers={"Authorization": f"Bearer {token}"},
                )
            ).status_code == 200
            assert (
                await client.get(
                    "/health",
                    headers={"Authorization": f"Bearer {token}"},
                )
            ).status_code == 200
            rebound = await client.get(
                "/v1/goals",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Host": "evil.example",
                },
            )
            assert rebound.status_code == 400
            assert rebound.json() == {"detail": "untrusted host"}

            state.token = ""
            assert (
                await client.get(
                    "/health/identity",
                    params={"challenge": challenge},
                )
            ).status_code == 503
            unavailable = await client.get(
                "/v1/goals",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert unavailable.status_code == 503
            assert unavailable.json()["detail"] == "bridge authentication is unavailable"
    finally:
        await store.close()


async def test_control_api_no_auth_is_available_only_to_explicit_test_settings(tmp_path):
    settings = Settings.for_test(require_auth=False, home=tmp_path, codex_attach=False)
    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = None
    await store.connect()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()),
            base_url="http://127.0.0.1",
        ) as client:
            assert (await client.get("/v1/goals")).status_code == 200
    finally:
        await store.close()


async def test_lifespan_preserves_owned_operator_token_over_fallback_file(tmp_path):
    operator = "tauri-owned-operator-token-that-is-long-enough"
    settings = Settings(
        require_auth=True,
        token=operator,
        home=tmp_path,
        codex_attach=False,
    )
    fallback = _load_or_create_bridge_token(settings.token_path)
    assert fallback != operator

    store = Store(tmp_path / "pex.sqlite")
    adapters = AdapterRegistry()
    bus = EventBus()
    state.settings = settings
    state.store = store
    state.adapters = adapters
    state.bus = bus
    state.pipeline = Pipeline(store, adapters, bus, settings)
    state.token = settings.token
    state.settings.token = None
    app = create_app()

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1",
        ) as client:
            challenge = "cd" * 32
            identity = await client.get(
                "/health/identity",
                params={"challenge": challenge},
            )
            assert identity.status_code == 200
            assert identity.json()["proof"] == hmac.new(
                operator.encode("ascii"),
                challenge.encode("ascii"),
                hashlib.sha256,
            ).hexdigest()
            assert (
                await client.get(
                    "/v1/goals",
                    headers={"Authorization": f"Bearer {operator}"},
                )
            ).status_code == 200
            assert (
                await client.get(
                    "/v1/goals",
                    headers={"Authorization": f"Bearer {fallback}"},
                )
            ).status_code == 401
            assert state.token == operator
            assert state.settings.token is None
