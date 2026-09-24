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


def test_load_rejects_exponent_overflow_before_schema_validation(tmp_path):
    path = tmp_path / "nonfinite.json"
    path.write_text(
        '{"version":1,"revision":1,"ignored":1e9999}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-finite JSON number"):
        load_supervisor_choice(path)


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


def test_secret_service_deleted_item_is_absent_and_delete_is_idempotent(monkeypatch):
    values: dict[tuple[str, str], str] = {}

    class ItemNotFoundException(Exception):
        pass

    ItemNotFoundException.__module__ = "secretstorage.exceptions"

    class SecretServiceKeyring:
        @staticmethod
        def set_password(service, reference, value):
            values[(service, reference)] = value

        @staticmethod
        def get_password(service, reference):
            try:
                return values[(service, reference)]
            except KeyError as exc:
                raise ItemNotFoundException("item is gone") from exc

        @staticmethod
        def delete_password(service, reference):
            try:
                del values[(service, reference)]
            except KeyError as exc:
                raise ItemNotFoundException("item is gone") from exc

    store = KeyringSupervisorSecretStore()
    monkeypatch.setattr(store, "_keyring", lambda: (SecretServiceKeyring, Exception))
    audience = "a" * 64
    reference = store.put("disposable", audience=audience)

    assert store.get(reference, audience=audience) == "disposable"
    store.delete(reference)
    assert store.get(reference, audience=audience) is None
    store.delete(reference)


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


def test_linux_keyring_chain_uses_secure_backend_without_plaintext_fallback(monkeypatch):
    from types import SimpleNamespace

    import keyring
    import pex_bridge.supervisor_config as config
    from keyring.backends.chainer import ChainerBackend

    values = {}

    class Secure:
        __module__ = "keyring.backends.SecretService"

        def set_password(self, service, name, value):
            values[service, name] = value

        def get_password(self, service, name):
            return values.get((service, name))

        def delete_password(self, service, name):
            values.pop((service, name))

    class Plaintext:
        __module__ = "keyrings.alt.file"

        def set_password(self, *_args):
            pytest.fail("plaintext backend must never receive the key")

    monkeypatch.setattr(config, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(ChainerBackend, "backends", [Plaintext(), Secure()])
    monkeypatch.setattr(keyring, "get_keyring", lambda: ChainerBackend())
    store = KeyringSupervisorSecretStore()
    reference = store.put("local-test-credential", audience="a" * 64)
    assert store.get(reference, audience="a" * 64) == "local-test-credential"
    store.delete(reference)
    assert not values


def test_keyring_chain_without_secure_backend_is_rejected(monkeypatch):
    import keyring
    from keyring.backends.chainer import ChainerBackend

    monkeypatch.setattr(ChainerBackend, "backends", [object()])
    monkeypatch.setattr(keyring, "get_keyring", lambda: ChainerBackend())
    with pytest.raises(SupervisorSecretStoreError, match="supported operating-system"):
        KeyringSupervisorSecretStore().put("local-test-credential", audience="a" * 64)


def test_keyring_initialization_failure_is_a_safe_configuration_error(monkeypatch):
    import keyring

    def unavailable():
        raise RuntimeError("private backend diagnostics")

    monkeypatch.setattr(keyring, "get_keyring", unavailable)
    with pytest.raises(SupervisorSecretStoreError, match="could not initialize") as error:
        KeyringSupervisorSecretStore()._keyring()
    assert "private backend diagnostics" not in str(error.value)
