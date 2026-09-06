import settings as S
from infra.db.engine import get_database_url


def test_get_database_url_uses_split_postgres_settings(monkeypatch):
    monkeypatch.setattr(S, "DATABASE_URL", None)
    monkeypatch.setattr(S, "POSTGRES_HOST", "db.internal")
    monkeypatch.setattr(S, "POSTGRES_PORT", 6543)
    monkeypatch.setattr(S, "POSTGRES_DB", "pithosys_test")
    monkeypatch.setattr(S, "POSTGRES_USER", "pithosys_user")
    monkeypatch.setattr(S, "POSTGRES_PASSWORD", "p@ss/word")

    assert (
        get_database_url()
        == "postgresql+psycopg://pithosys_user:p%40ss%2Fword@db.internal:6543/pithosys_test"
    )
