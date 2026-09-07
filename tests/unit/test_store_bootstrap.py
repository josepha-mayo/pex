"""Fresh schema setup is atomic without weakening durable SQLite settings."""

import sqlite3

import pytest
from pex_bridge.store import Store


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", [False, True])
async def test_failed_schema_setup_does_not_publish_partial_tables(tmp_path, monkeypatch, existing):
    import pex_bridge.store as store_module

    path = tmp_path / "pex.sqlite"
    if existing:
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE prior_data(value TEXT NOT NULL)")
            connection.execute("INSERT INTO prior_data VALUES ('preserve me')")
    original_schema = store_module.SCHEMA
    monkeypatch.setattr(store_module, "SCHEMA", original_schema + "\nINVALID SCHEMA STATEMENT;")
    store = Store(path)
    with pytest.raises(sqlite3.OperationalError):
        await store.connect()
    assert store._db is None
    with sqlite3.connect(path) as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert tables == ({"prior_data"} if existing else set())
        if existing:
            rows = connection.execute("SELECT value FROM prior_data").fetchall()
            assert rows == [("preserve me",)]

    monkeypatch.setattr(store_module, "SCHEMA", original_schema)
    await store.connect()
    try:
        async with store.db.execute("PRAGMA synchronous") as cursor:
            assert (await cursor.fetchone())[0] == 2  # FULL, never relaxed for startup speed.
        async with store.db.execute("PRAGMA journal_mode") as cursor:
            assert (await cursor.fetchone())[0] == "wal"
        assert not store.db.in_transaction
    finally:
        await store.close()
