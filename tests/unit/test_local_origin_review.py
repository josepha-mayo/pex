"""Independent configuration publication probes, restricted to pytest temp dirs."""

import pytest
from pex_bridge import local_origin_config as config
from pex_protocol.project_identity import ProjectOrigin


@pytest.mark.parametrize("change", ["replace", "modify"])
def test_changed_temporary_file_cannot_overwrite_verified_configuration(
    tmp_path, monkeypatch, change
):
    path = tmp_path / "origin.json"
    origin = ProjectOrigin(namespace="machine", host="explicit-review-label")
    previous = config.save_local_origin_choice(
        path, origin, expected_revision=None, expected_choice_id=None
    )
    before = path.read_bytes()
    actual_measure = config._measure_parent
    measurements = 0
    preserved = tmp_path / "preserved-original-temp"

    def replace_temp_after_writer_closes(candidate):
        nonlocal measurements
        measurements += 1
        measured = actual_measure(candidate)
        if measurements == 2:
            temporary, = tmp_path.glob(".origin.json.*.tmp")
            if change == "replace":
                temporary.rename(preserved)
            temporary.write_bytes(b"unowned replacement bytes")
        return measured

    monkeypatch.setattr(config, "_measure_parent", replace_temp_after_writer_closes)
    with pytest.raises(config.LocalOriginConfigError):
        config.save_local_origin_choice(
            path,
            origin,
            expected_revision=previous.revision,
            expected_choice_id=previous.choice_id,
        )

    # Rejection must happen before publishing a different actor's temporary file.
    assert path.read_bytes() == before
    assert config.load_local_origin_choice(path) == previous
    if change == "replace":
        assert preserved.is_file()
        replacement, = tmp_path.glob(".origin.json.*.tmp")
        assert replacement.read_bytes() == b"unowned replacement bytes"
    else:
        assert list(tmp_path.iterdir()) == [path]
