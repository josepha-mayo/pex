import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pex_protocol.goal import Goal
from pex_supervisor.verify import missing_required_files, verify_claims


def _goal(criterion):
    now = datetime.now(UTC)
    return Goal(id="g", project_id="p", title="Report", objective="Produce the report",
                acceptance_criteria=[criterion], created_at=now, updated_at=now)


@pytest.mark.parametrize("root", ["/public/workspace", "unclassified-workspace"])
def test_case_distinct_snapshot_file_does_not_satisfy_posix_or_unknown_root(root):
    workspace = {"workspace": root, "files": ["REPORT.json"]}
    assert missing_required_files(_goal("report.json exists"), workspace) == ["report.json"]


def test_windows_snapshot_retains_ascii_case_insensitive_matching():
    workspace = {"workspace": "Q:/public/workspace", "files": ["REPORT.json"]}
    assert missing_required_files(_goal("report.json exists"), workspace) == []


def test_posix_backslash_filename_does_not_alias_a_nested_artifact():
    workspace = {"workspace": "/public/workspace", "files": ["out\\report.json"]}
    assert missing_required_files(_goal("out/report.json exists"), workspace) == [
        "out/report.json",
    ]


def test_posix_row_verification_uses_the_exact_required_artifact():
    workspace = {
        "workspace": "/public/workspace", "files": ["REPORT.json", "report.json"],
        "artifacts": [
            {"path": "REPORT.json", "row_count": 20, "row_count_complete": True},
            {"path": "report.json", "row_count": 0, "row_count_complete": True},
        ],
    }
    result = verify_claims([], [], _goal("report.json has 20 rows"), workspace)
    assert result["status"] == "acceptance_gap"
    assert "contains 0 rows" in result["correction"]


def test_foreign_workspace_does_not_read_a_host_path_alias(monkeypatch):
    root = "/public/workspace" if os.name == "nt" else "Q:/public/workspace"
    workspace = {"workspace": root, "files": ["report.txt"]}

    def forbidden_resolve(*args, **kwargs):
        pytest.fail("foreign snapshot path was resolved against the controller host")

    monkeypatch.setattr(Path, "resolve", forbidden_resolve)
    result = verify_claims([], [], _goal("report.txt contains exactly `ok`"), workspace)
    assert result["acceptance_status"] == "uncertain"


@pytest.mark.skipif(sys.platform != "linux", reason="case-sensitive Linux filesystem required")
def test_actual_linux_file_with_different_case_is_not_the_deliverable(tmp_path):
    (tmp_path / "REPORT.json").write_text("[]")
    workspace = {"workspace": str(tmp_path), "files": ["REPORT.json"]}
    assert missing_required_files(_goal("report.json exists"), workspace) == ["report.json"]
