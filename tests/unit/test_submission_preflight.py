from __future__ import annotations

import hashlib
import importlib.util
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT_PATH = ROOT / "scripts" / "submission_preflight.py"


def _load_preflight():
    spec = importlib.util.spec_from_file_location("pex_submission_preflight", PREFLIGHT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _png(width: int, height: int) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    payload = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    chunk = b"IHDR" + payload
    return (
        signature
        + struct.pack(">I", len(payload))
        + chunk
        + struct.pack(">I", zlib.crc32(chunk))
    )


def test_video_url_accepts_only_public_video_hosts():
    module = _load_preflight()
    assert module.validate_video_url("https://youtu.be/example") is True
    assert module.validate_video_url("https://www.youtube.com/watch?v=example") is True
    assert module.validate_video_url("https://vimeo.com/12345") is True
    assert module.validate_video_url("http://youtu.be/example") is False
    assert module.validate_video_url("https://example.com/video") is False
    assert module.validate_video_url(None) is False


def test_png_dimensions_reads_ihdr_without_image_library(tmp_path):
    module = _load_preflight()
    path = tmp_path / "asset.png"
    path.write_bytes(_png(1600, 900))
    assert module.png_dimensions(path) == (1600, 900)


def test_artifact_check_fails_closed_on_size_or_hash_mismatch(tmp_path):
    module = _load_preflight()
    path = tmp_path / "artifact.bin"
    path.write_bytes(b"correct bytes")
    spec = module.ArtifactSpec(Path("artifact.bin"), 13, "0" * 64)
    result = module.artifact_check(tmp_path, spec)
    assert result["exists"] is True
    assert result["ok"] is False


def test_stale_scan_reports_missing_guides_and_old_receipts(tmp_path, monkeypatch):
    module = _load_preflight()
    monkeypatch.setattr(module, "ACTIVE_GUIDES", (Path("one.md"), Path("two.md")))
    (tmp_path / "one.md").write_text("old fc20329 receipt", encoding="utf-8")
    assert module.scan_stale_guides(tmp_path) == [
        {"path": "one.md", "pattern": "fc20329"},
        {"path": "two.md", "pattern": "missing"},
    ]


def test_sensitive_scan_redacts_values_and_ignores_test_canaries(tmp_path):
    module = _load_preflight()
    (tmp_path / "docs").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs" / "public.md").write_text(
        "credential sk-abcdefghijklmnopqrstuvwxyz",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "fixture.py").write_text(
        "token = 'sk-this-is-an-intentional-test-secret'",
        encoding="utf-8",
    )

    def runner(_root, *_args):
        return 0, "docs/public.md\ntests/fixture.py"

    canary = "sk-this-is-an-intentional-test-secret"
    module.SAFE_TEST_API_KEY_HASHES = frozenset(
        {hashlib.sha256(canary.encode("utf-8")).hexdigest()}
    )
    result = module.scan_tracked_sensitive_data(tmp_path, runner)
    assert result == {
        "readable": True,
        "hits": [{"path": "docs/public.md", "line": 1, "class": "api_key"}],
    }
    assert "abcdefghijklmnopqrstuvwxyz" not in str(result)


def test_sensitive_scan_fails_closed_when_git_listing_is_unavailable(tmp_path):
    module = _load_preflight()

    def runner(_root, *_args):
        return 1, ""

    assert module.scan_tracked_sensitive_data(tmp_path, runner) == {
        "readable": False,
        "hits": [],
    }


def test_git_check_requires_clean_tree_and_exact_remote_equality(tmp_path):
    module = _load_preflight()

    def clean_runner(_root, *args):
        command = " ".join(args)
        if command == "status --porcelain":
            return 0, ""
        return 0, "a" * 40

    assert module.git_check(tmp_path, clean_runner)["pushed"] is True

    def dirty_runner(_root, *args):
        if "status" in args:
            return 0, " M file"
        return 0, ("a" if "HEAD" in args else "b") * 40

    result = module.git_check(tmp_path, dirty_runner)
    assert result["clean"] is False
    assert result["pushed"] is False


def test_report_requires_every_manual_submission_gate(tmp_path, monkeypatch):
    module = _load_preflight()
    monkeypatch.setattr(module, "ARTIFACTS", ())
    monkeypatch.setattr(module, "ACTIVE_GUIDES", ())
    for name in ("README.md", "LICENSE", "devpost-submission.md"):
        (tmp_path / name).write_text("present", encoding="utf-8")

    def git_runner(_root, *_args):
        return 0, ""

    report = module.build_report(
        tmp_path,
        video_url=None,
        video_publicly_playable=False,
        architecture_attached=False,
        builder_id_confirmed=False,
        rules_accepted=False,
        git_runner=git_runner,
    )
    assert report["ready"] is False
    assert "public YouTube or Vimeo" in " ".join(report["blockers"])
    assert "logged-out demo video playback" in " ".join(report["blockers"])
    assert "architecture diagram" in " ".join(report["blockers"])
    assert "AWS Builder ID" in " ".join(report["blockers"])
    assert "official rules" in " ".join(report["blockers"])


def test_report_requires_playability_even_for_valid_video_url(tmp_path, monkeypatch):
    module = _load_preflight()
    monkeypatch.setattr(module, "ARTIFACTS", ())
    monkeypatch.setattr(module, "ACTIVE_GUIDES", ())
    monkeypatch.setattr(
        module,
        "scan_tracked_sensitive_data",
        lambda *_args: {"readable": True, "hits": []},
    )
    for name in ("README.md", "LICENSE", "devpost-submission.md"):
        (tmp_path / name).write_text("present", encoding="utf-8")

    def git_runner(_root, *args):
        if args == ("status", "--porcelain"):
            return 0, ""
        return 0, "a" * 40

    report = module.build_report(
        tmp_path,
        video_url="https://youtu.be/example",
        video_publicly_playable=False,
        architecture_attached=True,
        builder_id_confirmed=True,
        rules_accepted=True,
        git_runner=git_runner,
    )
    assert report["attestations"]["video_url_valid"] is True
    assert report["attestations"]["video_publicly_playable"] is False
    assert report["blockers"] == ["logged-out demo video playback is not attested"]
