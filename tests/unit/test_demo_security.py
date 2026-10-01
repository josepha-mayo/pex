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
