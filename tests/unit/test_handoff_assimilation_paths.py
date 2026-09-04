from pex_bridge.store import (
    _artifact_paths_match,
    _canonical_project_artifact_path,
)


def test_windows_absolute_paths_are_root_bound_and_case_insensitive() -> None:
    source = _canonical_project_artifact_path(
        r"C:\WORK\PEX\Artifacts\Prepared.parquet",
        project_id="C:/work/pex",
    )
    target = _canonical_project_artifact_path(
        r"c:\work\pex\artifacts\prepared.parquet",
        project_id="C:/work/pex",
    )

    assert source is not None
    assert target is not None
    assert source.windows_semantics is True
    assert _artifact_paths_match(source, target)
    assert (
        _canonical_project_artifact_path(
            r"C:\work\other\Artifacts\Prepared.parquet",
            project_id="C:/work/pex",
        )
        is None
    )
    assert (
        _canonical_project_artifact_path(
            r"\Artifacts\Prepared.parquet",
            project_id="C:/work/pex",
        )
        is None
    )


def test_posix_absolute_paths_are_root_bound_and_case_sensitive() -> None:
    upper = _canonical_project_artifact_path(
        "/work/pex/Artifacts/Prepared.parquet",
        project_id="/work/pex",
    )
    lower = _canonical_project_artifact_path(
        "/work/pex/artifacts/prepared.parquet",
        project_id="/work/pex",
    )

    assert upper is not None
    assert lower is not None
    assert upper.windows_semantics is False
    assert not _artifact_paths_match(upper, lower)
    assert (
        _canonical_project_artifact_path(
            "/work/pex/../secret.txt",
            project_id="/work/pex",
        )
        is None
    )
    assert (
        _canonical_project_artifact_path(
            "/work/other/Artifacts/Prepared.parquet",
            project_id="/work/pex",
        )
        is None
    )


def test_non_path_project_ids_accept_only_exact_safe_relative_paths() -> None:
    relative = _canonical_project_artifact_path(
        "artifacts/prepared.parquet",
        project_id="demo",
    )

    assert relative is not None
    assert relative.relative == "artifacts/prepared.parquet"
    assert relative.windows_semantics is False
    assert (
        _canonical_project_artifact_path(
            "../artifacts/prepared.parquet",
            project_id="demo",
        )
        is None
    )
    assert (
        _canonical_project_artifact_path(
            "C:/work/pex/artifacts/prepared.parquet",
            project_id="demo",
        )
        is None
    )
