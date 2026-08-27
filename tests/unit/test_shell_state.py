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


def test_non_pytest_command_is_ignored():
    assert parse_pytest_process_state("ls", {"output": "ok", "exit_code": 0}) is None
