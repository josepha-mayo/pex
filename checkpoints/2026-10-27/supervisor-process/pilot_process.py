"""One approved private pilot only; production invoke_live remains unchanged.

Root must independently pin the private configuration digest. No environment flag,
worker supplied configuration, or fixture receipt grants admission. No API call is
made by constructing the model. Credentials stay in this trusted controller process.
"""
import hashlib
import importlib
import json
import os
import re
import stat
from contextlib import aclosing
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

APPROVAL_REF = "Sentinel_a6f9e81f1aa88191a915b10436a3cb06"
PILOT_ID = "pex-paired-pilot-20261027-101349"
# Internal conservative execution limit, NOT a user-stated expiry.
EXECUTION_END = "2026-10-27T14:00:00+00:00"
ENDPOINT = "https://api.tokenfactory.us-central1.nebius.com/v1/chat/completions"
MODEL = "nvidia/nemotron-3-super-120b-a12b"
SOURCE_MODULES = (
    "pilot_process", "process_adapter", "accounting", "managed_chat",
    "managed_tool_chat", "strands_bridge", "tool_protocol", "pex_protocol.actions",
    "pex_protocol.supervisor", "pex_supervisor.loop", "pex_supervisor.evidence_tools",
    "pex_supervisor.evidence_observations",
)
PACKAGES = {"strands-agents": "1.53.0", "httpx": "0.28.1", "opentelemetry-api": "1.45.1"}
_RUNTIMES = {}


def _private_bytes(path, limit):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError("private path must be absolute and unlinked")
    parent = path.parent.stat()
    if parent.st_uid != os.geteuid() or stat.S_IMODE(parent.st_mode) & 0o077:
        raise ValueError("private directory permissions required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077
                or info.st_size > limit):
            raise ValueError("private file permissions/type/size refused")
        data = os.read(fd, limit + 1)
        if len(data) > limit:
            raise ValueError("private file size refused")
        return data
    finally:
        os.close(fd)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate private configuration field")
        result[key] = value
    return result


def _check_telemetry():
    from opentelemetry import metrics, trace
    if (type(trace.get_tracer_provider()) is not trace.NoOpTracerProvider
            or type(metrics.get_meter_provider()) is not metrics.NoOpMeterProvider):
        raise RuntimeError("fresh NoOp controller process required")


def _load_config(path, expected_sha):
    _check_telemetry()
    if type(expected_sha) is not str or not re.fullmatch(r"[a-f0-9]{64}", expected_sha):
        raise ValueError("independent private configuration digest required")
    raw = _private_bytes(path, 65536)
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("private configuration digest mismatch")
    config = json.loads(raw, object_pairs_hook=_pairs)
    required = {"schema", "approval_ref", "pilot_id", "expires_at", "endpoint", "model",
                "budget_nano_usd", "max_attempts", "input_rate", "output_rate",
                "pricing_provenance_sha256", "key_path", "key_sha256", "ledger_path",
                "source_sha256", "request_binding"}
    if type(config) is not dict or set(config) != required:
        raise ValueError("private configuration schema refused")
    exact = {"schema": 1, "approval_ref": APPROVAL_REF, "pilot_id": PILOT_ID,
             "endpoint": ENDPOINT, "model": MODEL, "budget_nano_usd": 250000000,
             "max_attempts": 12, "input_rate": 300, "output_rate": 900}
    if any(type(config[k]) is not type(v) or config[k] != v for k, v in exact.items()):
        raise ValueError("approved pilot configuration mismatch")
    expires = datetime.fromisoformat(config["expires_at"])
    if (expires.tzinfo is None or expires > datetime.fromisoformat(EXECUTION_END)
            or datetime.now(timezone.utc) >= expires):
        raise ValueError("pilot execution expired or invalid")
    for name in ("pricing_provenance_sha256", "key_sha256"):
        if type(config[name]) is not str or not re.fullmatch(r"[a-f0-9]{64}", config[name]):
            raise ValueError("private digest missing")
    binding = config["request_binding"]
    if (type(binding) is not dict or set(binding) != {"goal_id", "session_id", "vendor_session_id"}
            or any(type(v) is not str or not v or len(v) > 256 for v in binding.values())):
        raise ValueError("pilot request binding required")
    sources = config["source_sha256"]
    if type(sources) is not dict or set(sources) != set(SOURCE_MODULES):
        raise ValueError("complete trusted source binding required")
    for name, expected in sources.items():
        if type(expected) is not str or not re.fullmatch(r"[a-f0-9]{64}", expected):
            raise ValueError("trusted source digest invalid")
        module = importlib.import_module(name)
        source = Path(module.__file__)
        if source.resolve() != source or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError("trusted source identity mismatch")
    if any(version(name) != expected for name, expected in PACKAGES.items()):
        raise ValueError("trusted dependency version mismatch")
    ledger = Path(config["ledger_path"])
    if (not ledger.is_absolute() or ledger.parent != Path(path).parent
            or ledger.name != "supervisor-pilot.sqlite" or ledger.is_symlink()):
        raise ValueError("pilot ledger private binding refused")
    if ledger.exists():
        _private_bytes(ledger, 16 * 1024 * 1024)
    return config


def pilot_routes():
    from managed_chat import Limits, Route
    return tuple(Route(ENDPOINT, MODEL, role, Limits(max_output_tokens=cap,
                 max_usage_tokens=266240, timeout_seconds=60))
                 for role, cap in (("planner", 1200), ("verifier", 900)))


class _PilotRuntime:
    def __init__(self, path, digest, config):
        from accounting import Ledger
        self.path, self.digest = Path(path), digest
        self.routes = pilot_routes()
        self.ledger = Ledger(Path(config["ledger_path"]), budget=250000000,
            input_rate=300, output_rate=900, route=self.routes[0], currency="USD",
            pricing_provenance_sha256=config["pricing_provenance_sha256"],
            input_token_bound=262144, output_token_bound=4096,
            approved_routes=self.routes, max_attempts=12)
        db = self.ledger.db
        db.execute("CREATE TABLE IF NOT EXISTS pilot_admission (digest TEXT, state TEXT)")
        db.execute("BEGIN IMMEDIATE")
        try:
            rows = db.execute("SELECT * FROM pilot_admission").fetchall()
            if not rows:
                # Admission cannot claim an existing unbound spending ledger.
                if db.execute("SELECT COUNT(*) FROM calls").fetchone()[0]:
                    raise ValueError("unbound prior pilot spending refused")
                db.execute("INSERT INTO pilot_admission VALUES (?,?)", (digest, "active"))
            elif rows != [(digest, "active")]:
                raise ValueError("pilot admission already closed or changed")
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            self.ledger.close()
            raise

    def validate(self):
        config = _load_config(self.path, self.digest)
        if self.ledger.db.execute("SELECT * FROM pilot_admission").fetchall() != [(self.digest, "active")]:
            raise ValueError("pilot admission closed")
        return config

    def credential(self, route):
        from managed_chat import _ScopedCredential
        config = self.validate()
        raw = _private_bytes(config["key_path"], 16384)
        if hashlib.sha256(raw).hexdigest() != config["key_sha256"]:
            raise ValueError("private credential identity mismatch")
        try:
            key = raw.decode("ascii").strip()
        except UnicodeError:
            raise ValueError("private credential encoding refused") from None
        return _ScopedCredential(key, route.fingerprint)


def pilot_model(private_config_path, request, *, invocation_id, proposal=None,
                expected_config_sha256=None):
    """Trusted root-only factory. No network calls until invoke_async is awaited."""
    config = _load_config(private_config_path, expected_config_sha256)
    binding = config["request_binding"]
    if (request.goal is None or request.goal.id != binding["goal_id"]
            or request.session.id != binding["session_id"]
            or request.session.vendor_session_id != binding["vendor_session_id"]):
        raise ValueError("request outside approved pilot session")
    cache_key = (str(Path(private_config_path)), expected_config_sha256)
    runtime = _RUNTIMES.get(cache_key)
    if runtime is None:
        runtime = _PilotRuntime(private_config_path, expected_config_sha256, config)
        _RUNTIMES[cache_key] = runtime
    runtime.validate()
    route = runtime.routes[0 if proposal is None else 1]
    from managed_tool_chat import ManagedToolChatCandidate
    from strands_bridge import ManagedPEXModel

    class AccountedPilotCandidate(ManagedToolChatCandidate):
        async def _execute_owned(self, invocation, credential):
            runtime.validate()
            runtime.ledger.reserve(invocation.invocation_id, self.route)
            try:
                return await super()._execute_owned(invocation, credential)
            finally:
                runtime.ledger.settle(invocation.invocation_id, self.receipt(invocation.invocation_id))

    class PilotModel(ManagedPEXModel):
        async def invoke_async(self):
            runtime.validate()
            return await self._invoke_owned_agent()

        async def stream(self, *args, **kwargs):
            credential = runtime.credential(route)
            async with aclosing(self._stream_owned(*args, credential=credential, **kwargs)) as stream:
                async for event in stream:
                    yield event

    model = PilotModel(route, request, invocation_id=invocation_id, proposal=proposal)
    model._candidate = AccountedPilotCandidate(route, model.protocol)
    return model


def close_pilot(private_config_path, *, expected_config_sha256):
    """Controller cleanup: terminal even if credentials are revoked separately."""
    runtime = _RUNTIMES.pop((str(Path(private_config_path)), expected_config_sha256), None)
    if runtime is not None:
        runtime.ledger.db.execute("UPDATE pilot_admission SET state='closed' WHERE digest=?", (expected_config_sha256,))
        runtime.ledger.close()
