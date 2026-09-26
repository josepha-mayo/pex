import hashlib
import zipfile

import pytest

from benchmarks import linux_supervisor_runtime as runtime


def _fixture(tmp_path, monkeypatch, member="dependency.py", *, locked=True):
    repo = tmp_path / "repo"
    repo.mkdir()
    for relative, _ in runtime.PACKAGES:
        source = repo / relative
        source.mkdir(parents=True)
        (source / "__init__.py").write_text("# public package\n")
        (source / ".env").write_text("PRIVATE=must-not-copy\n")
    benchmark = repo / "benchmarks"
    benchmark.mkdir()
    (benchmark / "pex_supervisor_process.py").write_text("# public decision process\n")
    (benchmark / "evaluator.py").write_text("# private oracle must not be bundled\n")
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    wheel = wheels / "test.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        info = zipfile.ZipInfo("placeholder")
        info.filename = member
        archive.writestr(info, "# dependency\n")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (repo / "uv.lock").write_text(f"sha256:{digest}\n" if locked else "")
    monkeypatch.setattr(runtime, "REPO", repo)
    return wheels, tmp_path / "runtime"


def test_runtime_contains_only_public_sources_and_hashed_dependencies(tmp_path, monkeypatch):
    wheels, destination = _fixture(tmp_path, monkeypatch)
    manifest = runtime.build_runtime(wheels, destination)
    assert manifest["model_transport"] == "disabled"
    paths = {row["path"] for row in manifest["files"]}
    assert "public_process.py" in paths
    assert "site-packages/dependency.py" in paths
    assert not any("evaluator" in path or ".env" in path for path in paths)
    for row in manifest["files"]:
        assert hashlib.sha256((destination / row["path"]).read_bytes()).hexdigest() == row["sha256"]
    with pytest.raises(ValueError, match="fresh"):
        runtime.build_runtime(wheels, destination)


@pytest.mark.parametrize("member", ["../oracle.py", "/oracle.py", "bad\\file.py", "C:bad.py"])
def test_runtime_refuses_unsafe_wheel_paths_before_writing(tmp_path, monkeypatch, member):
    wheels, destination = _fixture(tmp_path, monkeypatch, member)
    with pytest.raises(ValueError, match="unsafe path"):
        runtime.build_runtime(wheels, destination)
    assert not destination.exists()


def test_runtime_refuses_unlocked_dependency_wheel(tmp_path, monkeypatch):
    wheels, destination = _fixture(tmp_path, monkeypatch, locked=False)
    with pytest.raises(ValueError, match="uv.lock"):
        runtime.build_runtime(wheels, destination)
    assert not destination.exists()
