import uuid

from infra.db.capabilities import detect_capabilities
from infra.db.repositories.search_portable import build_portable_search_store
from infra.db.repositories.search_postgres import build_postgres_search_store
from ports.repositories.search import SearchStore
from sqlalchemy.orm import Session


def build_search_store(session: Session) -> SearchStore:
    caps = detect_capabilities(session.get_bind())
    if caps.json_contains:
        return build_postgres_search_store(session)
    return build_portable_search_store(session)
