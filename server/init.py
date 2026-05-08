import os

from ducklake_client import DuckLake, PostgresCatalog, S3Storage

lake = DuckLake(
    catalog=PostgresCatalog(
        dsn="postgresql://relic:relic@localhost:5432/relic",
    ),
    storage=S3Storage(
        bucket="relic",
        endpoint="http://localhost:3900",
        region="garage",
        key_id=os.getenv("S3_HOT_ACCESS_KEY"),
        secret_access_key=os.getenv("S3_HOT_SECRET_KEY"),
    ),
)


def main():
    print("Hello from server!")
    test = lake.sql_one("SELECT 1")
    print(test)


if __name__ == "__main__":
    main()
