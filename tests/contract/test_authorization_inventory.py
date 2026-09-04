from __future__ import annotations

import ast
from pathlib import Path

EXPECTED_GATES = {
    "test_live_agentcore.py::test_live_agentcore_returns_bound_strands_decision": (
        "PEX_AGENTCORE_LIVE",
    ),
    "test_live_claude_stop.py::test_live_claude_incomplete_stop_sends_specific_context": (
        "PEX_LIVE_SUPERVISOR",
    ),
    "test_live_codex.py::test_live_codex_appserver_handshake": ("PEX_LIVE_CODEX",),
    "test_live_codex_pump.py::test_live_codex_app_server_stop_reaches_ingest": (
        "PEX_LIVE_CODEX",
    ),
    "test_live_codex_pump.py::test_live_codex_stop_inspects_with_strands": (
        "PEX_LIVE_CODEX",
        "PEX_LIVE_SUPERVISOR",
    ),
    "test_live_codex_pump.py::test_live_codex_incomplete_stop_sends_specific_continue": (
        "PEX_LIVE_CODEX",
        "PEX_LIVE_SUPERVISOR",
    ),
    "test_live_cursor_stop.py::test_live_cursor_incomplete_stop_sends_specific_followup": (
        "PEX_LIVE_SUPERVISOR",
    ),
    "test_live_devin_stop.py::test_live_devin_exit_sends_specific_message": (
        "PEX_LIVE_SUPERVISOR",
    ),
    "test_live_grok_build_stop.py::test_grok_build_hook_without_acp_does_not_claim_delivery": (
        "PEX_LIVE_SUPERVISOR",
    ),
    "test_live_hermes_stop.py::test_live_hermes_session_end_does_not_fake_context_without_acp": (
        "PEX_LIVE_SUPERVISOR",
    ),
    "test_live_kimi_stop.py::test_live_kimi_prompt_result_sends_specific_prompt": (
        "PEX_LIVE_SUPERVISOR",
    ),
    "test_live_omp_stop.py::test_live_omp_prompt_result_sends_specific_prompt": (
        "PEX_LIVE_SUPERVISOR",
    ),
    "test_live_opencode.py::test_live_opencode_attach_is_deep": ("PEX_LIVE_OPENCODE",),
    "test_live_opencode_stop.py::test_live_opencode_idle_stop_sends_specific_prompt": (
        "PEX_LIVE_SUPERVISOR",
    ),
    "test_live_qwen_stop.py::test_live_qwen_turn_complete_sends_specific_prompt": (
        "PEX_LIVE_SUPERVISOR",
    ),
    "test_live_supervisor.py::test_live_supervisor_inference_is_auditable": (
        "PEX_LIVE_SUPERVISOR",
    ),
}


def _first_executable(node: ast.AsyncFunctionDef | ast.FunctionDef) -> ast.stmt:
    body = list(node.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body.pop(0)
    assert body, f"{node.name} has no executable body"
    return body[0]


def _gate_flags(statement: ast.stmt) -> tuple[str, ...]:
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
        call = statement.value
        if isinstance(call.func, ast.Name) and call.func.id == "require_live_authorization":
            return tuple(
                str(arg.value)
                for arg in call.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            )
    rendered = ast.unparse(statement)
    if "PEX_AGENTCORE_LIVE" in rendered and "pytest.skip" in rendered:
        return ("PEX_AGENTCORE_LIVE",)
    return ()


def test_every_live_contract_has_an_explicit_first_statement_gate():
    found: dict[str, tuple[str, ...]] = {}
    for path in sorted(Path(__file__).parent.glob("test_live_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name.startswith(
                "test_"
            ):
                found[f"{path.name}::{node.name}"] = _gate_flags(_first_executable(node))

    assert found == EXPECTED_GATES


def test_codex_live_supervisor_tests_configure_local_endpoint_before_model_load():
    path = Path(__file__).parent / "test_live_codex_pump.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    expected = {
        "test_live_codex_stop_inspects_with_strands",
        "test_live_codex_incomplete_stop_sends_specific_continue",
    }
    checked: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.AsyncFunctionDef) or node.name not in expected:
            continue
        calls = [item for item in ast.walk(node) if isinstance(item, ast.Call)]

        def call_lines(name: str, *, calls: list[ast.Call] = calls) -> list[int]:
            return [
                item.lineno
                for item in calls
                if isinstance(item.func, ast.Name) and item.func.id == name
            ]

        configured = call_lines("_ensure_local_supervisor_env")
        loaded = call_lines("load_supervisor_model")
        assert len(configured) == len(loaded) == 1
        assert configured[0] < loaded[0]
        checked.add(node.name)
    assert checked == expected
