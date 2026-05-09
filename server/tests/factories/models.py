import factory

from models import Blob, Bucket
from schema_plan import BucketTier


class BucketFactory(factory.Factory):
    class Meta:
        model = Bucket

    name = factory.Sequence(lambda n: f"garage-{n}")
    endpoint = "http://garage-hot:3900"
    region = "garage"
    bucket = "blobs"
    key_id = factory.Sequence(lambda n: f"GK{n:024d}")
    secret_access_key = factory.Sequence(lambda n: f"secret-{n}")
    tier = BucketTier.HOT
    max_size_bytes = 1_000_000_000


class BlobFactory(factory.Factory):
    class Meta:
        model = Blob

    bucket_id = None
    bucket_key = factory.Sequence(lambda n: f"objects/{n}")
    content_hash = factory.Sequence(lambda n: n.to_bytes(32, "big"))
    refcount = 1
