from tests.db import create_test_engine, upgrade_test_schema


def test_alembic_upgrade_head_on_sqlite():
    engine = create_test_engine()
    upgrade_test_schema(engine)
    with engine.connect() as conn:
        tables = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"
        ).fetchall()
    names = {row[0] for row in tables}
    assert "files" in names
    assert "blobs" in names
    assert "audit_events" in names
    assert "processors" not in names
