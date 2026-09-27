import hashlib

import pytest

from benchmarks.opencode_runtime import build_runtime, measure_profile


def runtime(tmp_path):
    binary = tmp_path / "source-opencode"
    binary.write_bytes(b"pinned binary test fixture")
    return build_runtime(tmp_path / "runtime", binary=binary,
                         expected_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())


def test_runtime_is_public_only_and_profile_binds_binary_modules_and_settings(tmp_path):
    root = runtime(tmp_path)
    first = measure_profile(root, model="pinned")
    assert first == measure_profile(root, model="pinned")
    changed_model = measure_profile(root, model="different")
    assert first["runtime_sha256"] == changed_model["runtime_sha256"]
    assert first["settings_sha256"] != changed_model["settings_sha256"]
    (root / "opencode").chmod(0o755)
    (root / "opencode").write_bytes(b"different binary")
    assert first["runtime_sha256"] != measure_profile(root, model="pinned")["runtime_sha256"]


@pytest.mark.parametrize("mutation", ["extra", "source", "init"])
def test_runtime_cannot_include_private_files_or_drifted_modules(tmp_path, mutation):
    root = runtime(tmp_path)
    if mutation == "extra":
        (root / "evaluator.py").write_text("private evaluator")
    elif mutation == "source":
        (root / "benchmarks/opencode_worker.py").write_text("changed worker")
    else:
        (root / "benchmarks/__init__.py").write_text("unexpected startup code")
    with pytest.raises(ValueError):
        measure_profile(root, model="pinned")


def test_unpinned_binary_cannot_reserve_runtime_directory(tmp_path):
    binary = tmp_path / "source-opencode"
    binary.write_bytes(b"wrong binary")
    with pytest.raises(ValueError, match="pinned digest"):
        build_runtime(tmp_path / "runtime", binary=binary, expected_binary_sha256="a" * 64)
    assert not (tmp_path / "runtime").exists()
