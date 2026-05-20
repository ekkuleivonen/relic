import uuid
from typing import Protocol

from domain.files.search import SearchQuery
from infra.db.models import File


class SearchStore(Protocol):
    def match_files(
        self, *, scope_folder_ids: set[uuid.UUID], query: SearchQuery
    ) -> list[File]: ...
