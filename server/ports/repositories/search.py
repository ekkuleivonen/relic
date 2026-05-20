import uuid
from dataclasses import dataclass
from typing import Protocol

from domain.files.search import SearchQuery
from infra.db.models import File


@dataclass(frozen=True)
class SearchPage:
    items: list[File]
    total: int


class SearchStore(Protocol):
    def search_page(
        self, *, scope_folder_ids: set[uuid.UUID], query: SearchQuery
    ) -> SearchPage: ...

    def match_files(
        self, *, scope_folder_ids: set[uuid.UUID], query: SearchQuery
    ) -> list[File]: ...
