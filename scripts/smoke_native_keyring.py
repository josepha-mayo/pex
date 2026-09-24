"""Exercise the actual OS credential backend with a disposable fake secret."""

from __future__ import annotations

import hashlib
import secrets

from pex_bridge.supervisor_config import (
    KeyringSupervisorSecretStore,
    SupervisorSecretStoreError,
)


def main() -> None:
    store = KeyringSupervisorSecretStore()
    backend, _ = store._keyring()
    secret = "pex-smoke-" + secrets.token_urlsafe(24)
    audience = hashlib.sha256(b"pex-native-keyring-smoke").hexdigest()
    wrong_audience = hashlib.sha256(b"pex-wrong-keyring-audience").hexdigest()
    reference = store.put(secret, audience=audience)
    try:
        if store.get(reference, audience=audience) != secret:
            raise AssertionError("OS credential roundtrip did not preserve the fake secret")
        try:
            store.get(reference, audience=wrong_audience)
        except SupervisorSecretStoreError:
            pass
        else:
            raise AssertionError("OS credential accepted the wrong audience")
    finally:
        store.delete(reference)
    if store.get(reference, audience=audience) is not None:
        raise AssertionError("OS credential remained after deletion")
    store.delete(reference)
    selected = backend.get_keyring() if hasattr(backend, "get_keyring") else backend
    print(f"Native keyring roundtrip passed ({type(selected).__module__})")


if __name__ == "__main__":
    main()
