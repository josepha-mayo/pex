from pex_bridge.pets import PetSettings, catalog, shipping_pet_settings


def test_retired_selection_migrates_without_destroying_preferences():
    original = PetSettings(selected_id="ledger", custom_name="Buddy", scale=0.8)
    migrated = shipping_pet_settings(original)
    assert migrated.selected_id == "pex"
    assert migrated.custom_name == "Buddy"
    assert migrated.scale == 0.8
    assert original.selected_id == "ledger"


def test_both_shipping_selections_are_preserved():
    for pet_id in ("pex", "von"):
        settings = PetSettings(selected_id=pet_id)
        assert shipping_pet_settings(settings) is settings


def test_current_catalog_does_not_scan_legacy_imports(monkeypatch):
    def unexpected_scan(_imported):
        raise AssertionError("MVP must not read imported pet files")

    monkeypatch.setattr("pex_bridge.pets._validated_imported_sheet", unexpected_scan)
    settings = PetSettings(imports=[{
        "id": "import:old-cat",
        "display_name": "Old cat",
        "directory": "C:/legacy/pet",
        "spritesheet": "C:/legacy/pet/spritesheet.webp",
    }], selected_id="import:old-cat")
    assert [pet.id for pet in catalog(settings)] == ["pex", "von"]
    migrated = shipping_pet_settings(settings)
    assert migrated.selected_id == "pex"
    assert migrated.imports == settings.imports
