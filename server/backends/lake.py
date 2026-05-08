import os

from dotenv import load_dotenv
from ducklake_client import DuckLake, PostgresCatalog, S3Storage

load_dotenv()

lake = DuckLake(
    catalog=PostgresCatalog(
        dsn=os.getenv("POSTGRES_DSN"),
    ),
    storage=S3Storage(
        bucket=os.getenv("S3_LAKE_BUCKET"),
        endpoint=os.getenv("S3_HOT_ENDPOINT"),
        region=os.getenv("S3_HOT_REGION"),
        key_id=os.getenv("S3_HOT_ACCESS_KEY"),
        secret_access_key=os.getenv("S3_HOT_SECRET_KEY"),
    ),
)
