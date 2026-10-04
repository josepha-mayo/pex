"""ConTree sandbox backend: contract-bound behavior against a fake transport."""

import base64
import hashlib
from pathlib import Path

import pytest
from pex_bridge import observe
from pex_bridge.contree import (
    DEFAULT_IMAGE,
    EXECUTOR,
    TransportResponse,
    contree_config,
    public_pytest_backend,
    run_public_pytest_contree,
)
from pex_protocol.isolated_pytest import isolated_pytest_argv


def _b64(text: str) -> dict:
    return {"value": base64.b64encode(text.encode()).decode(), "encoding": "base64"}


def _operation(status: str, result=None, error=None):
    body = {
        "uuid": "aaaaaaaa-0000-0000-0000-0000000000aa",
        "kind": "instance",
        "status": status,
        "duration": 1.5,
        "consumed_cpu": 0.4,
        "consumed_memory": 4096,
        "image_uuid": "bbbbbbbb-0000-0000-0000-0000000000bb",
        "result_image_uuid": "cccccccc-0000-0000-0000-0000000000cc",
    }
    if result is not None:
        body["result"] = result
    if error is not None:
        body["error"] = error
    return body


def _instance_result(exit_code: int, stdout: str = "", stderr: str = "", timed_out=False):
    return {
        "state": {"exit_code": exit_code, "timed_out": timed_out},
        "stdout": _b64(stdout),
        "stderr": _b64(stderr),
    }


class FakeTransport:
    """Scripted ConTree API; unknown files 404 until POSTed."""

    def __init__(
        self,
        statuses=None,
        files=None,
        spawn_status=201,
        spawn_body=None,
        spawn_headers=None,
        file_status=404,
        upload_status=201,
    ):
        self.statuses = list(statuses or [_operation("SUCCESS", _instance_result(0))])
        self.known_files = dict(files or {})
        self.spawn_status = spawn_status
        self.spawn_body = spawn_body or {"uuid": "dddddddd-0000-0000-0000-0000000000dd"}
        self.spawn_headers = (
            spawn_headers
            if spawn_headers is not None
            else {"location": "/v1/operations/eeeeeeee-0000-0000-0000-0000000000ee"}
        )
        self.file_status = file_status
        self.upload_status = upload_status
        self.calls = []
        self.spawn_payload = None
        self.cancelled = []
        self.uploaded_contents = {}

    def request(self, method, path, *, json_body=None, content=None, headers=None):
        self.calls.append((method, path))
        if method == "GET" and path.startswith("/files/"):
            sha = path.rsplit("/", 1)[-1]
            if sha in self.known_files:
                return TransportResponse(
                    200, {}, {"uuid": self.known_files[sha], "sha256": sha, "size": 1}
                )
            return TransportResponse(self.file_status, {}, {"error": "missing"})
        if method == "POST" and path == "/files":
            sha = hashlib.sha256(content).hexdigest()
            file_uuid = self.known_files.setdefault(
                sha, f"11111111-0000-0000-0000-{len(self.known_files):012d}"[-36:]
            )
            self.uploaded_contents[sha] = content
            return TransportResponse(
                self.upload_status, {}, {"uuid": file_uuid, "sha256": sha, "size": len(content)}
            )
        if method == "POST" and path == "/instances":
            self.spawn_payload = json_body
            return TransportResponse(self.spawn_status, self.spawn_headers, self.spawn_body)
        if method == "GET" and path.startswith("/operations/"):
            if self.statuses:
                body = self.statuses.pop(0)
                return TransportResponse(200, {"retry-after": "0"}, body)
            return TransportResponse(200, {}, _operation("EXECUTING"))
        if method == "DELETE" and path.startswith("/operations/"):
            self.cancelled.append(path.rsplit("/", 1)[-1])
            return TransportResponse(200, {}, {})
        raise AssertionError(f"unexpected request {method} {path}")


def _workspace(tmp_path: Path, files: dict[str, str]) -> list[dict]:
    manifest = []
    for rel, text in files.items():
        path = tmp_path.joinpath(*rel.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode()
        path.write_bytes(data)
        manifest.append(
            {
                "path": rel,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
            }
        )
    return manifest


_TEST_CONFIG_ENV = {"PEX_CONTREE_API_KEY": "k", "PEX_CONTREE_PROJECT": "p"}


def _run(tmp_path, manifest, tests, transport, **kwargs):
    kwargs.setdefault("sleeper", lambda seconds: None)
    kwargs.setdefault("config", contree_config(_TEST_CONFIG_ENV))
    return run_public_pytest_contree(tmp_path, manifest, tests, transport=transport, **kwargs)


def test_contree_run_executes_isolated_argv_in_a_disposable_vm(tmp_path):
    manifest = _workspace(
        tmp_path,
        {
            "app.py": "def add(a, b): return a + b\n",
            "test_app.py": "from app import add\ndef test_add():\n    assert add(1, 2) == 3\n",
        },
    )
    transport = FakeTransport(
        statuses=[
            _operation("PENDING"),
            _operation("EXECUTING"),
            _operation("SUCCESS", _instance_result(0, "1 passed\n")),
        ]
    )
    result = _run(tmp_path, manifest, ["test_app.py"], transport)
    assert result["ok"] is True
    assert result["exit_code"] == 0
    assert "1 passed" in result["output"]
    assert result["executor"] == EXECUTOR
    assert result["argv"] == isolated_pytest_argv("/usr/local/bin/python3", ["test_app.py"])

    payload = transport.spawn_payload
    assert payload["command"] == "/usr/local/bin/python3"
    assert payload["args"] == result["argv"][1:]
    assert payload["shell"] is False
    assert payload["networking"] == {"enabled": False}
    assert payload["disposable"] is True
    assert payload["cwd"] == "/workspace"
    assert payload["env"]["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] == "1"
    assert payload["files"]["/workspace/test_app.py"]["uuid"]
    assert payload["files"]["/workspace/app.py"]["uuid"]

    provenance = result["sandbox"]
    assert provenance["operation_uuid"] == "eeeeeeee-0000-0000-0000-0000000000ee"
    assert provenance["instance_uuid"] == "dddddddd-0000-0000-0000-0000000000dd"
    assert provenance["image_uuid"] == "bbbbbbbb-0000-0000-0000-0000000000bb"


def test_contree_run_reports_test_failures_as_test_evidence(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "def test_a():\n    assert False\n"})
    transport = FakeTransport(
        statuses=[_operation("SUCCESS", _instance_result(1, "F\n1 failed\n"))]
    )
    result = _run(tmp_path, manifest, ["test_a.py"], transport)
    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert "error_type" not in result
    assert "1 failed" in result["output"]


def test_contree_dedupes_uploads_by_manifest_sha256(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "def test_a():\n    pass\n"})
    known = {manifest[0]["sha256"]: "ffffffff-0000-0000-0000-0000000000ff"}
    transport = FakeTransport(files=known)
    result = _run(tmp_path, manifest, ["test_a.py"], transport)
    assert result["ok"] is True
    assert not any(method == "POST" and path == "/files" for method, path in transport.calls)
    assert (
        transport.spawn_payload["files"]["/workspace/test_a.py"]["uuid"]
        == "ffffffff-0000-0000-0000-0000000000ff"
    )


def test_contree_refuses_files_that_drifted_since_the_manifest(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "def test_a():\n    pass\n"})
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert False\n")
    transport = FakeTransport()
    result = _run(tmp_path, manifest, ["test_a.py"], transport)
    assert result["ok"] is False
    assert result["error_type"] == "workspace_drift"
    assert transport.spawn_payload is None


def test_contree_auth_failure_is_an_infra_error_not_a_test_result(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "def test_a():\n    pass\n"})
    transport = FakeTransport(spawn_status=401, spawn_body={"error": "bad token"})
    result = _run(tmp_path, manifest, ["test_a.py"], transport)
    assert result["ok"] is False
    assert result["exit_code"] is None
    assert result["error_type"] == "auth"


def test_contree_failed_operation_is_not_misreported_as_a_test_run(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "def test_a():\n    pass\n"})
    transport = FakeTransport(statuses=[_operation("FAILED", error="image pull failed")])
    result = _run(tmp_path, manifest, ["test_a.py"], transport)
    assert result["ok"] is False
    assert result["exit_code"] is None
    assert result["error_type"] == "operation_failed"
    assert "image pull failed" in result["error"]


def test_contree_deadline_cancels_the_operation_and_reports_timeout(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "def test_a():\n    pass\n"})
    transport = FakeTransport(statuses=[_operation("EXECUTING")] * 100)
    clock = {"now": 0.0}

    def monotonic():
        clock["now"] += 5.0
        return clock["now"]

    def sleeper(_seconds):
        pass

    result = run_public_pytest_contree(
        tmp_path,
        manifest,
        ["test_a.py"],
        deadline=45.0,
        transport=transport,
        config=contree_config(_TEST_CONFIG_ENV),
        monotonic=monotonic,
        sleeper=sleeper,
    )
    assert result["ok"] is False
    assert result["timed_out"] is True
    assert result["error_type"] == "timeout"
    assert transport.cancelled


def test_contree_process_timeout_maps_to_timed_out(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "def test_a():\n    pass\n"})
    transport = FakeTransport(
        statuses=[_operation("SUCCESS", _instance_result(124, "", "", timed_out=True))]
    )
    result = _run(tmp_path, manifest, ["test_a.py"], transport)
    assert result["ok"] is False
    assert result["timed_out"] is True
    assert "timed out after" in result["output"]


def test_contree_spawn_without_operation_location_is_malformed(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "def test_a():\n    pass\n"})
    transport = FakeTransport(spawn_headers={})
    result = _run(tmp_path, manifest, ["test_a.py"], transport)
    assert result["error_type"] == "malformed"


def test_contree_missing_pytest_in_image_is_not_a_test_failure(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "def test_a():\n    pass\n"})
    transport = FakeTransport(
        statuses=[
            _operation(
                "SUCCESS",
                _instance_result(1, stderr="python3: No module named pytest\n"),
            )
        ]
    )
    result = _run(tmp_path, manifest, ["test_a.py"], transport)
    assert result["ok"] is False
    assert result["error_type"] == "sandbox_image_missing_pytest"


def test_contree_withholds_hidden_marker_output(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "def test_a():\n    pass\n"})
    transport = FakeTransport(
        statuses=[
            _operation(
                "SUCCESS",
                _instance_result(1, "hint: see evaluator.py for the answer\n"),
            )
        ]
    )
    result = _run(tmp_path, manifest, ["test_a.py"], transport)
    assert result["output"] == "[public pytest output withheld: hidden benchmark marker detected]"


def test_contree_missing_credentials_fail_closed(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "def test_a():\n    pass\n"})
    transport = FakeTransport()
    config = contree_config({})
    result = run_public_pytest_contree(
        tmp_path,
        manifest,
        ["test_a.py"],
        transport=transport,
        config=config,
        sleeper=lambda s: None,
    )
    assert result["ok"] is False
    assert result["error_type"] == "unconfigured"
    assert transport.calls == []


def test_contree_upload_bound_refuses_oversized_workspaces(tmp_path):
    manifest = _workspace(tmp_path, {"test_a.py": "x" * 64 + "\ndef test_a():\n    pass\n"})
    config = contree_config(
        {
            "PEX_CONTREE_API_KEY": "k",
            "PEX_CONTREE_PROJECT": "p",
            "PEX_CONTREE_MAX_UPLOAD_BYTES": "8",
        }
    )
    result = run_public_pytest_contree(
        tmp_path,
        manifest,
        ["test_a.py"],
        transport=FakeTransport(),
        config=config,
        sleeper=lambda s: None,
    )
    assert result["ok"] is False
    assert result["error_type"] == "workspace_bound"


def test_contree_config_env_parsing(monkeypatch):
    for name in (
        "PEX_CONTREE_API_KEY",
        "NEBIUS_API_KEY",
        "PEX_CONTREE_PROJECT",
        "NEBIUS_PROJECT_ID",
        "PEX_CONTREE_IMAGE",
        "PEX_CONTREE_TIMEOUT_SECONDS",
        "PEX_CONTREE_MAX_UPLOAD_BYTES",
        "PEX_CONTREE_MAX_FILES",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("NEBIUS_API_KEY", "nb")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "proj")
    monkeypatch.setenv("PEX_CONTREE_TIMEOUT_SECONDS", "99999")
    config = contree_config()
    assert config.api_key == "nb"
    assert config.project == "proj"
    assert config.timeout_seconds == 300
    assert config.image == DEFAULT_IMAGE
    assert config.missing_reasons() == []


def test_public_pytest_backend_env(monkeypatch):
    monkeypatch.delenv("PEX_PUBLIC_PYTEST_BACKEND", raising=False)
    assert public_pytest_backend() == ""
    monkeypatch.setenv("PEX_PUBLIC_PYTEST_BACKEND", " Contree ")
    assert public_pytest_backend() == "contree"


def test_observe_routes_public_pytest_to_contree_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("PEX_PUBLIC_PYTEST_BACKEND", "contree")
    calls = {}

    def fake_contree(root, manifest, tests, **kwargs):
        calls["manifest"] = manifest
        calls["tests"] = tests
        return {"ok": True, "executor": EXECUTOR}

    import pex_bridge.contree as contree

    monkeypatch.setattr(contree, "run_public_pytest_contree", fake_contree)
    monkeypatch.setattr(observe.subprocess, "Popen", lambda *a, **k: pytest.fail("local exec"))
    (tmp_path / "test_a.py").write_text("def test_a():\n    pass\n")
    result = observe.snapshot(tmp_path, run_pytest=True)
    assert result["pytest"] == {"ok": True, "executor": EXECUTOR}
    assert calls["tests"] == ["test_a.py"]
    assert calls["manifest"]


def test_observe_contree_backend_never_falls_back_to_local_exec(tmp_path, monkeypatch):
    monkeypatch.setenv("PEX_PUBLIC_PYTEST_BACKEND", "contree")
    for name in (
        "PEX_CONTREE_API_KEY",
        "NEBIUS_API_KEY",
        "PEX_CONTREE_PROJECT",
        "NEBIUS_PROJECT_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(observe.subprocess, "Popen", lambda *a, **k: pytest.fail("local exec"))
    (tmp_path / "test_a.py").write_text("def test_a():\n    pass\n")
    result = observe.snapshot(tmp_path, run_pytest=True)
    assert result["pytest"]["ok"] is False
    assert result["pytest"]["error_type"] == "unconfigured"


def test_observe_defaults_to_local_public_pytest(tmp_path, monkeypatch):
    monkeypatch.delenv("PEX_PUBLIC_PYTEST_BACKEND", raising=False)
    (tmp_path / "test_a.py").write_text("def test_a():\n    assert True\n")
    result = observe.snapshot(tmp_path, run_pytest=True)
    assert result["pytest"]["ok"] is True
    assert result["pytest"]["exit_code"] == 0
    assert "executor" not in result["pytest"]
