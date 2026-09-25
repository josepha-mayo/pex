"""Native acceptance regression: explicit LF prose must stay byte-exact."""

import pytest
from pex_supervisor.verify import _expected_content, verify_claims
from pex_supervisor.workspace import snapshot
from test_verify import _goal


@pytest.mark.parametrize(
    "suffix",
    [
        "one LF newline",
        "one LF newline (U+000A)",
        "one LF newline (U+000A), no CR",
        "a single LF newline, no CR.",
    ],
)
@pytest.mark.parametrize(
    "content,expected",
    [(b"ready\n", "supported"), (b"readx\n", "unsatisfied"),
     (b"ready\r\n", "unsatisfied"), (b"ready", "unsatisfied"),
     (b"ready\n\n", "unsatisfied")],
)
def test_explicit_lf_acceptance_checks_the_whole_file(tmp_path, suffix, content, expected):
    (tmp_path / "status.txt").write_bytes(content)
    result = verify_claims(
        [], [],
        _goal(acceptance_criteria=[f"status.txt contains exactly ready followed by {suffix}"],
              evidence_requirements=[]),
        snapshot(tmp_path, run_pytest=False),
    )
    assert result["acceptance_status"] == expected


@pytest.mark.parametrize(
    "suffix",
    ["one CRLF newline", "one LF newline (U+000D)",
     "one LF newline or a CRLF newline", "one LF newline, CR allowed",
     "one LF newline (U+000A), no CR and any extra text"],
)
def test_unsupported_newline_prose_is_not_silently_weakened(suffix):
    assert _expected_content(f"status.txt contains exactly ready followed by {suffix}") is None


def test_missing_exact_artifact_routes_its_content_into_the_worker_correction(tmp_path):
    result = verify_claims(
        [], [],
        _goal(
            acceptance_criteria=[
                "final.txt contains exactly pex-supervised-ok followed by one newline"
            ],
            evidence_requirements=["final.txt"],
        ),
        snapshot(tmp_path, run_pytest=False),
    )
    assert result["acceptance_status"] == "unsatisfied"
    assert "exact content 'pex-supervised-ok\\n'" in result["correction"]
    assert "current workspace" in result["correction"]
