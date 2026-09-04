from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pex_bridge.supervisor_config import (
    MAX_SUPERVISOR_CHOICE_BYTES,
    KeyringSupervisorSecretStore,
    SupervisorChoice,
    SupervisorSecretStoreError,
    load_supervisor_choice,
    save_supervisor_choice,
)


def test_choice_persists_only_an_opaque_reference_and_public_view_omits_it(tmp_path):
    canary = "sk-winning-canary-must-never-be-persisted"
    choice = SupervisorChoice(
        provider="custom",
        model_id="winner-model",
        auth_mode="custom",
        protocol="anthropic",
        base_url="https://models.example.invalid/v1",
        credential_source="secret_store",
        secret_ref="sec_0123456789abcdef0123456789abcdef",
    )
    path = tmp_path / "supervisor.json"

    save_supervisor_choice(path, choice)
    raw = path.read_text(encoding="utf-8")
    loaded = load_supervisor_choice(path)
    public = choice.public_dict(has_api_key=True)

    assert loaded == choice
    assert canary not in raw
    assert canary not in repr(choice)
    assert "secret_ref" not in public
    assert "sec_0123456789abcdef0123456789abcdef" not in json.dumps(public)
    assert public["credential_configured"] is True
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_credential_audience_changes_for_every_routing_boundary():
    base = SupervisorChoice(
        provider="custom",
        model_id="model-a",
        auth_mode="custom",
        protocol="openai",
        base_url="https://one.example.invalid/v1",
    )
    assert base.credential_audience() == base.model_copy(
        update={"model_id": "model-b"}
    ).credential_audience()
    for update in (
        {"provider": "openrouter"},
        {"auth_mode": "api_key"},
        {"protocol": "anthropic"},
        {"base_url": "https://two.example.invalid/v1"},
    ):
        assert base.credential_audience() != base.model_copy(
            update=update
        ).credential_audience()


def test_load_migrates_original_two_field_choice_without_inventing_a_secret(tmp_path):
    path = tmp_path / "supervisor.json"
    path.write_text(
        json.dumps({"provider": "openrouter", "model_id": "model"}),
        encoding="utf-8",
    )

    loaded = load_supervisor_choice(path)

    assert loaded is not None
    assert loaded.version == 1
    assert loaded.revision == 1
    assert loaded.credential_source == "environment"
    assert loaded.secret_ref is None


def test_load_rejects_duplicate_keys_oversize_and_symlink(tmp_path):
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"version":1,"version":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        load_supervisor_choice(duplicate)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (MAX_SUPERVISOR_CHOICE_BYTES + 1))
    with pytest.raises(ValueError, match="safety bound"):
        load_supervisor_choice(oversized)

    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    linked = tmp_path / "linked.json"
    try:
        linked.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable in this test environment")
    with pytest.raises(ValueError, match="symbolic link"):
        load_supervisor_choice(linked)


def test_keyring_envelope_is_versioned_bounded_and_audience_bound(monkeypatch):
    values: dict[tuple[str, str], str] = {}

    class FakeKeyringError(Exception):
        pass

    class FakeKeyring:
        @staticmethod
        def set_password(service, reference, value):
            values[(service, reference)] = value

        @staticmethod
        def get_password(service, reference):
            return values.get((service, reference))

        @staticmethod
        def delete_password(service, reference):
            values.pop((service, reference), None)

    store = KeyringSupervisorSecretStore()
    monkeypatch.setattr(store, "_keyring", lambda: (FakeKeyring, FakeKeyringError))
    audience = "a" * 64

    reference = store.put("key-canary", audience=audience)

    envelope = json.loads(values[(store.service_name, reference)])
    assert envelope == {
        "version": 1,
        "audience": audience,
        "secret": "key-canary",
    }
    assert store.get(reference, audience=audience) == "key-canary"
    with pytest.raises(SupervisorSecretStoreError, match="audience mismatch"):
        store.get(reference, audience="b" * 64)

    values[(store.service_name, reference)] = (
        '{"version":1,"audience":"' + audience + '","secret":"one","secret":"two"}'
    )
    with pytest.raises(SupervisorSecretStoreError, match="invalid.*envelope"):
        store.get(reference, audience=audience)

    store.delete(reference)
    assert (store.service_name, reference) not in values


@pytest.mark.skipif(os.name != "nt", reason="this receipt targets the Windows desktop build")
def test_windows_runtime_selects_winvault_not_a_plaintext_keyring():
    store = KeyringSupervisorSecretStore()

    keyring_module, _error = store._keyring()

    assert type(keyring_module.get_keyring()).__module__ == "keyring.backends.Windows"


def test_frozen_sidecar_collects_dynamic_keyring_backends():
    repo = Path(__file__).resolve().parents[2]
    build_script = (repo / "apps" / "desktop" / "scripts" / "build-sidecar.mjs").read_text(
        encoding="utf-8"
    )

    assert '"--collect-all",\n    "keyring"' in build_script
