from __future__ import annotations

import json

import pytest
from pex_bridge.demo import list_fixtures, load_fixture


def test_demo_fixture_id_cannot_escape_fixture_directory(tmp_path, monkeypatch) -> None:
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    (tmp_path / "secret.json").write_text(
        json.dumps({"events": [], "secret": "do-not-read"}),
        encoding="utf-8",
    )
    monkeypatch.setattr("pex_bridge.demo.fixture_dir", lambda: fixture_dir)

    with pytest.raises(ValueError, match="invalid demo fixture id"):
        load_fixture("../secret")


def test_demo_fixture_is_bounded_and_structurally_validated(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("pex_bridge.demo.fixture_dir", lambda: tmp_path)
    (tmp_path / "array.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="contain an object"):
        load_fixture("array")

    (tmp_path / "many.json").write_text(
        json.dumps({"events": [{}] * 1001}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="at most 1000"):
        load_fixture("many")

    (tmp_path / "large.json").write_bytes(b"{" + b"x" * 1_048_576)
    with pytest.raises(ValueError, match="1 MiB"):
        load_fixture("large")


def test_demo_listing_skips_malformed_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("pex_bridge.demo.fixture_dir", lambda: tmp_path)
    (tmp_path / "good.json").write_text(
        json.dumps({"id": "good", "title": "Good", "events": [{"event_type": "status"}]}),
        encoding="utf-8",
    )
    (tmp_path / "bad.json").write_text("not-json", encoding="utf-8")

    assert list_fixtures() == [
        {
            "id": "good",
            "title": "Good",
            "replay": True,
            "not_live_control": True,
            "events": 1,
        }
    ]


def test_demo_listing_surfaces_bounded_summary(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("pex_bridge.demo.fixture_dir", lambda: tmp_path)
    (tmp_path / "arc.json").write_text(
        json.dumps(
            {
                "id": "arc",
                "title": "Arc",
                "summary": "  " + "x" * 300,
                "events": [{"event_type": "status"}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "nonstr.json").write_text(
        json.dumps(
            {"id": "nonstr", "title": "Nonstr", "summary": 7, "events": []}
        ),
        encoding="utf-8",
    )

    items = {item["id"]: item for item in list_fixtures()}
    assert items["arc"]["summary"] == "x" * 240
    assert "summary" not in items["nonstr"]


@pytest.mark.parametrize(
    "payload",
    [
        '{"events": [], "score": NaN}',
        '{"events": [], "score": Infinity}',
        '{"events": [], "ignored": 1e9999}',
        '{"events": [], "events": [{}]}',
    ],
)
def test_demo_fixture_rejects_non_strict_json(tmp_path, monkeypatch, payload: str) -> None:
    monkeypatch.setattr("pex_bridge.demo.fixture_dir", lambda: tmp_path)
    (tmp_path / "invalid.json").write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        load_fixture("invalid")


@pytest.mark.parametrize(
    "relpath",
    ["../escape.py", "/abs/path.py", "a\\b.py", "C:/x.py", ".", "a//b.py"],
)
def test_demo_workspace_rejects_unsafe_paths(tmp_path, monkeypatch, relpath) -> None:
    monkeypatch.setattr("pex_bridge.demo.fixture_dir", lambda: tmp_path)
    (tmp_path / "ws.json").write_text(
        json.dumps({"events": [], "workspace": {"files": {relpath: "x"}}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="relative POSIX"):
        load_fixture("ws")


def test_demo_workspace_is_bounded(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("pex_bridge.demo.fixture_dir", lambda: tmp_path)
    (tmp_path / "bigfile.json").write_text(
        json.dumps(
            {"events": [], "workspace": {"files": {"big.py": "x" * 65_537}}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="64 KiB"):
        load_fixture("bigfile")

    (tmp_path / "manyfiles.json").write_text(
        json.dumps(
            {
                "events": [],
                "workspace": {"files": {f"f{i}.py": "x" for i in range(65)}},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="bounded object"):
        load_fixture("manyfiles")

    (tmp_path / "badmutation.json").write_text(
        json.dumps(
            {
                "events": [],
                "workspace": {
                    "files": {},
                    "mutations": [{"after": "0", "files": {"a.py": "x"}}],
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="event index"):
        load_fixture("badmutation")


def test_demo_materialize_stays_under_root(tmp_path) -> None:
    from pex_bridge.demo import materialize_workspace

    materialize_workspace(tmp_path, {"tests/a.py": "pass\n", "b/c.txt": "hi"})
    assert (tmp_path / "tests" / "a.py").read_text() == "pass\n"
    assert (tmp_path / "b" / "c.txt").read_text() == "hi"


def test_demo_mutation_delete_is_validated_and_applied(tmp_path, monkeypatch) -> None:
    from pex_bridge.demo import materialize_workspace, remove_workspace_files

    monkeypatch.setattr("pex_bridge.demo.fixture_dir", lambda: tmp_path)
    (tmp_path / "del.json").write_text(
        json.dumps(
            {
                "events": [{"event_type": "status"}],
                "workspace": {
                    "files": {"pytest.ini": "[pytest]\n", "t/a.py": "x"},
                    "mutations": [{"after": 0, "delete": ["pytest.ini"]}],
                },
            }
        ),
        encoding="utf-8",
    )

    fixture = load_fixture("del")
    assert fixture["workspace"]["mutations"][0]["delete"] == ["pytest.ini"]

    materialize_workspace(tmp_path / "ws", {"pytest.ini": "[pytest]\n", "t/a.py": "x"})
    root = tmp_path / "ws"
    remove_workspace_files(root, ["pytest.ini"])
    assert not (root / "pytest.ini").exists()
    assert (root / "t" / "a.py").exists()


def test_demo_mutation_delete_rejects_unsafe_and_missing(tmp_path, monkeypatch) -> None:
    from pex_bridge.demo import materialize_workspace, remove_workspace_files

    monkeypatch.setattr("pex_bridge.demo.fixture_dir", lambda: tmp_path)
    (tmp_path / "bad.json").write_text(
        json.dumps(
            {
                "events": [{"event_type": "status"}],
                "workspace": {"mutations": [{"after": 0, "delete": ["../x.py"]}]},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="relative POSIX"):
        load_fixture("bad")

    materialize_workspace(tmp_path / "ws", {"a.py": "x"})
    with pytest.raises(FileNotFoundError):
        remove_workspace_files(tmp_path / "ws", ["never-wrote.py"])


def test_demo_fixtures_load_from_repo() -> None:
    """Shipped fixtures stay loadable — the judge demo path depends on them."""

    fixture_ids = {item["id"] for item in list_fixtures()}
    assert "tampered_acceptance_eval" in fixture_ids
    assert "config_injection_eval" in fixture_ids
    for fixture_id in fixture_ids:
        assert load_fixture(fixture_id)["not_live_control"] is True


def test_inline_fixture_passes_through_the_same_gate() -> None:
    """A judge-authored body is validated by the identical loader path."""

    from pex_bridge.demo import parse_inline_fixture

    data = parse_inline_fixture(
        {
            "title": "judge attack",
            "goal": {"title": "t", "objective": "o"},
            "events": [{"event_type": "stop"}],
            "workspace": {"files": {"a.py": "x"}},
        }
    )
    assert data["replay"] is True
    assert data["not_live_control"] is True

    with pytest.raises(ValueError, match="relative POSIX"):
        parse_inline_fixture(
            {"events": [], "workspace": {"files": {"../escape.py": "x"}}}
        )
    with pytest.raises(ValueError, match="at most 1000"):
        parse_inline_fixture({"events": [{}] * 1001})
    with pytest.raises(ValueError, match="64 KiB"):
        parse_inline_fixture(
            {"events": [], "workspace": {"files": {"big.py": "x" * 65_537}}}
        )


def test_inline_fixture_rejects_non_finite_and_non_serializable() -> None:
    from pex_bridge.demo import parse_inline_fixture

    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        parse_inline_fixture({"events": [], "score": float("nan")})
    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        parse_inline_fixture({"events": [], "score": float("inf")})
    with pytest.raises(ValueError, match="JSON-serializable"):
        parse_inline_fixture({"events": [], "x": object()})
    with pytest.raises(ValueError, match="contain an object"):
        parse_inline_fixture(["not", "a", "dict"])
