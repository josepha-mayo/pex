import pytest
from pex_bridge.shell_state import parse_pytest_process_state


def test_pytest_failure_output_becomes_process_state():
    state = parse_pytest_process_state(
        "pytest -q",
        {
            "exit_code": 1,
            "output": "FAILED tests/test_parser.py::test_nested_array\n1 failed, 0 passed",
        },
    )
    assert state is not None
    assert state["pytest"]["ok"] is False
    assert state["pytest"]["failed"] == "tests/test_parser.py::test_nested_array"
    assert state["pytest"]["exit_code"] == 1


def test_powershell_wrapped_pytest_failure_becomes_typed_process_state():
    state = parse_pytest_process_state(
        r'"C:\runtime\pwsh.exe" -Command '
        "'C:/workspace/.venv/Scripts/python.exe -m pytest -q test_normalizer.py'",
        {
            "exit_code": 1,
            "output": "FAILED test_normalizer.py::test_trim\n4 failed in 0.31s",
        },
    )

    assert state == {
        "pytest": {
            "ok": False,
            "output": "FAILED test_normalizer.py::test_trim\n4 failed in 0.31s",
            "exit_code": 1,
            "failed_count": 4,
            "failed": "test_normalizer.py::test_trim",
        }
    }


def test_non_pytest_command_is_ignored():
    assert parse_pytest_process_state("ls", {"output": "ok", "exit_code": 0}) is None


@pytest.mark.parametrize(
    "command",
    [
        "echo pytest -q 12 passed",
        "cat pytest.log",
        "pytest --collect-only",
        "pytest --help",
        "pytest --version",
        "pytest -q > pytest.log",
        "pytest -q | tee pytest.log",
        "pytest -q && echo done",
        "pytest -q || true",
    ],
)
def test_spoofed_or_non_test_pytest_commands_do_not_create_process_state(command):
    assert (
        parse_pytest_process_state(
            command,
            {"exit_code": 0, "output": "999 passed in 0.01s"},
        )
        is None
    )


def test_payload_mentions_cannot_substitute_for_an_actual_pytest_command():
    assert (
        parse_pytest_process_state(
            "python -c print(1)",
            {
                "tool_name": "pytest_runner",
                "output": "pytest -q\n999 passed in 0.01s",
                "exit_code": 0,
            },
        )
        is None
    )


def test_codex_completed_status_is_not_exit_zero():
    state = parse_pytest_process_state(
        "pytest -q",
        {
            "status": "completed",
            "aggregatedOutput": "FAILED tests/test_parser.py::test_nested_array\n1 failed",
        },
    )
    assert state is not None
    assert state["pytest"]["ok"] is False
    assert state["pytest"].get("exit_code") is None
    assert state["pytest"]["failed"] == "tests/test_parser.py::test_nested_array"
