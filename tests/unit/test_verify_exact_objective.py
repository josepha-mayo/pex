"""A weaker substring criterion must not erase an explicit exact-file objective."""

import pytest
from pex_supervisor.verify import verify_claims
from pex_supervisor.workspace import snapshot
from test_verify import _goal


@pytest.mark.parametrize("verb", ["Create", "Write", "Update"])
@pytest.mark.parametrize("content,expected", [
    (b"pong", "supported"),
    (b"\xef\xbb\xbfpong", "unsatisfied"),
    (b"pong\n", "unsatisfied"),
    (b"prefix pong", "unsatisfied"),
])
def test_exact_objective_survives_weaker_contains_criterion(tmp_path, verb, content, expected):
    (tmp_path / "ping.txt").write_bytes(content)
    result = verify_claims([], [], _goal(
        objective=f"{verb} ping.txt containing exactly the word pong.",
        acceptance_criteria=["ping.txt contains pong"], evidence_requirements=["ping.txt"],
    ), snapshot(tmp_path, run_pytest=False))
    assert result["acceptance_status"] == expected


def test_plain_contains_objective_does_not_invent_byte_exactness(tmp_path):
    (tmp_path / "ping.txt").write_bytes(b"prefix pong suffix")
    result = verify_claims([], [], _goal(
        objective="Create ping.txt containing pong.",
        acceptance_criteria=["ping.txt contains pong"], evidence_requirements=["ping.txt"],
    ), snapshot(tmp_path, run_pytest=False))
    assert result["acceptance_status"] == "supported"
