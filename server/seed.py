from backends import lake
from ducklake_client import ColumnDef


def main():
    # Physical bytes, immutable, shared by metadata references
    lake.table.create(
        "blobs",
        id=ColumnDef("UUID"),
        storage_key=ColumnDef("VARCHAR"),
        content_hash=ColumnDef("VARCHAR"),
        name_original=ColumnDef("VARCHAR"),
        file_size=ColumnDef("BIGINT"),
        mime_type=ColumnDef("VARCHAR"),
        extension=ColumnDef("VARCHAR"),
        storage_tier=ColumnDef("INTEGER"),
        created_at=ColumnDef("TIMESTAMP"),
        accessed_at=ColumnDef("TIMESTAMP"),
    )
    # Logical file references to blobs, mutable, throwaway
    lake.table.create(
        "files",
        id=ColumnDef("UUID"),
        name=ColumnDef("VARCHAR"),
        created_at=ColumnDef("TIMESTAMP"),
        updated_at=ColumnDef("TIMESTAMP"),
        meta=ColumnDef("JSON"),
        blob_id=ColumnDef("UUID"),
        folder_id=ColumnDef("UUID"),
    )

    # Folders for the virtual filesystem. Access gates & metadata schema validation.
    lake.table.create(
        "folders",
        id=ColumnDef("UUID"),
        name=ColumnDef("VARCHAR"),
        schema=ColumnDef("JSON"),
        created_at=ColumnDef("TIMESTAMP"),
        updated_at=ColumnDef("TIMESTAMP"),
        parent_id=ColumnDef("UUID"),
    )

    test = lake.table.list()
    for table in test:
        print(table.qualified_name)

    print("Done!")


if __name__ == "__main__":
    main()
