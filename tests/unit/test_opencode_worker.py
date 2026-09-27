import json
import time

import pytest

from benchmarks import opencode_worker as worker


@pytest.mark.parametrize("supervised", [False, True])
async def test_common_worker_environment_has_no_host_credentials_and_condition_only_review(
    tmp_path, monkeypatch, supervised,
):
    captured = {}
    monkeypatch.setattr(worker.sys, "platform", "linux")
    monkeypatch.setenv("OPENAI_API_KEY", "host-key-canary")
    monkeypatch.setenv("OPENCODE_CONFIG_CONTENT", "host-config-canary")

    async def session(**options):
        captured.update(options)
        return "completed"

    monkeypatch.setattr(worker, "run_session", session)
    result = await worker.run_worker(
        executable=tmp_path / "opencode", workspace=tmp_path / "workspace",
        socket_path=str(tmp_path / "relay.sock"), model="pinned", prompt="public task",
        log_directory=tmp_path / "logs", state_home=tmp_path / "state",
        deadline=time.monotonic() + 10, supervised=supervised, max_followups=0,
    )
    assert result == "completed"
    environment = captured["environment"]
    assert "OPENAI_API_KEY" not in environment and "host-config-canary" not in str(environment)
    settings = json.loads(environment["OPENCODE_CONFIG_CONTENT"])
    assert settings["enabled_providers"] == ["controlled"]
    assert settings["permission"]["read"] == settings["permission"]["bash"] == "allow"
    assert settings["permission"]["*"] == "deny"
    assert settings["share"] == "disabled"
    assert (captured["review"] is not None) == supervised
    assert captured["model"] == "controlled/pinned"
    with pytest.raises(FileExistsError):
        await worker.run_worker(
            executable=tmp_path / "opencode", workspace=tmp_path / "workspace",
            socket_path=str(tmp_path / "relay.sock"), model="pinned", prompt="public task",
            log_directory=tmp_path / "other-logs", state_home=tmp_path / "state",
            deadline=time.monotonic() + 10, supervised=supervised, max_followups=0,
        )


async def test_expired_worker_never_opens_proxy_or_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(worker.sys, "platform", "linux")

    def forbidden(*args, **kwargs):
        pytest.fail("expired worker must not open a proxy")

    monkeypatch.setattr(worker, "make_server", forbidden)
    with pytest.raises(TimeoutError):
        await worker.run_worker(
            executable=tmp_path / "opencode", workspace=tmp_path / "workspace",
            socket_path=str(tmp_path / "relay.sock"), model="pinned", prompt="public task",
            log_directory=tmp_path / "logs", state_home=tmp_path / "state",
            deadline=time.monotonic() - 1, supervised=False, max_followups=0,
        )
    assert not (tmp_path / "logs").exists()


async def test_proxy_teardown_cannot_publish_success_after_shared_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(worker.sys, "platform", "linux")
    clock = [100.0]
    monkeypatch.setattr(worker, "monotonic", lambda: clock[0])
    original = worker.make_server

    def make_server(*args, **kwargs):
        server = original(*args, **kwargs)
        close = server.server_close

        def late_close():
            close()
            clock[0] = 102.0

        server.server_close = late_close
        return server

    async def session(**options):
        clock[0] = 100.9
        return "too late to publish"

    monkeypatch.setattr(worker, "make_server", make_server)
    monkeypatch.setattr(worker, "run_session", session)
    with pytest.raises(TimeoutError, match="teardown"):
        await worker.run_worker(
            executable=tmp_path / "opencode", workspace=tmp_path / "workspace",
            socket_path=str(tmp_path / "relay.sock"), model="pinned", prompt="public task",
            log_directory=tmp_path / "logs", state_home=tmp_path / "state",
            deadline=101, supervised=False, max_followups=0,
        )
