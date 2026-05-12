import settings as S
from database import get_database_url


def test_get_database_url_uses_split_postgres_settings(monkeypatch):
    monkeypatch.setattr(S, "POSTGRES_HOST", "db.internal")
    monkeypatch.setattr(S, "POSTGRES_PORT", 6543)
    monkeypatch.setattr(S, "POSTGRES_DB", "relic_test")
    monkeypatch.setattr(S, "POSTGRES_USER", "relic_user")
    monkeypatch.setattr(S, "POSTGRES_PASSWORD", "p@ss/word")

    assert (
        get_database_url()
        == "postgresql+psycopg://relic_user:p%40ss%2Fword@db.internal:6543/relic_test"
    )
