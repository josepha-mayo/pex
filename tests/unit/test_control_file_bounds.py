from __future__ import annotations

import pytest
from pex_bridge.app import _read_bounded_utf8, _strict_json_loads
from pex_bridge.pets import ImportedPet, PetSettings
from pydantic import ValidationError


def test_bounded_control_file_reader_rejects_oversize_and_invalid_utf8(tmp_path) -> None:
    path = tmp_path / "control.json"
    path.write_bytes(b"x" * 17)
    with pytest.raises(ValueError, match="safety bound"):
        _read_bounded_utf8(path, 16, "control file")

    path.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        _read_bounded_utf8(path, 16, "control file")


@pytest.mark.parametrize(
    "payload",
    ['{"choice": NaN}', '{"choice": "first", "choice": "second"}'],
)
def test_control_file_json_is_strict(payload: str) -> None:
    with pytest.raises(ValueError):
        _strict_json_loads(payload)


def test_pet_settings_bound_import_count_and_persisted_fields() -> None:
    pet = ImportedPet(
        id="import:test",
        display_name="Test",
        directory="C:/pets/test",
        spritesheet="C:/pets/test/spritesheet.webp",
    )
    with pytest.raises(ValidationError):
        PetSettings(imports=[pet] * 65)
    with pytest.raises(ValidationError):
        ImportedPet(
            id="import:../../escape",
            display_name="Test",
            directory="C:/pets/test",
            spritesheet="C:/pets/test/spritesheet.webp",
        )
