from __future__ import annotations

import pytest
from pex_bridge.store import Store


@pytest.mark.asyncio
async def test_intervention_binding_migration_marker_is_stable_on_reconnect(tmp_path):
    path = tmp_path / "pex.sqlite"
    store = Store(path)
    await store.connect()
    try:
        cursor = await store.db.execute(
            "SELECT initialized_at, legacy_unbound_count, schema_version, json "
            "FROM intervention_binding_migration_state WHERE singleton = 1"
        )
        first = dict(await cursor.fetchone())
    finally:
        await store.close()

    restarted = Store(path)
    await restarted.connect()
    try:
        cursor = await restarted.db.execute(
            "SELECT initialized_at, legacy_unbound_count, schema_version, json "
            "FROM intervention_binding_migration_state WHERE singleton = 1"
        )
        assert dict(await cursor.fetchone()) == first
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_corrupt_intervention_binding_migration_marker_fails_reconnect(tmp_path):
    path = tmp_path / "pex.sqlite"
    store = Store(path)
    await store.connect()
    try:
        await store.db.execute(
            "DROP TRIGGER trg_intervention_binding_migration_immutable"
        )
        await store.db.execute(
            "UPDATE intervention_binding_migration_state SET json = '{}' "
            "WHERE singleton = 1"
        )
        await store.db.commit()
    finally:
        await store.close()

    restarted = Store(path)
    with pytest.raises(RuntimeError, match="migration marker is corrupt"):
        await restarted.connect()
