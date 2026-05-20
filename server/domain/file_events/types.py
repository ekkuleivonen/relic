"""File event type constants for the integrator subscription log."""

FILE_EVENT_CREATED = "file.created"
FILE_EVENT_CONTENT_UPDATED = "file.content_updated"
FILE_EVENT_META_UPDATED = "file.meta_updated"
FILE_EVENT_RENAMED = "file.renamed"
FILE_EVENT_MOVED = "file.moved"
FILE_EVENT_DELETED = "file.deleted"

FILE_EVENT_TYPES = frozenset(
    {
        FILE_EVENT_CREATED,
        FILE_EVENT_CONTENT_UPDATED,
        FILE_EVENT_META_UPDATED,
        FILE_EVENT_RENAMED,
        FILE_EVENT_MOVED,
        FILE_EVENT_DELETED,
    }
)

FILE_EVENT_ORIGINS = frozenset({"upload", "multipart", "copy", "duplicate"})
