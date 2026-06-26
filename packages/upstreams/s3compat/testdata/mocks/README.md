# S3-Compatible Upstream Fixtures

These fixtures represent raw HTTP responses from S3-compatible object APIs.

`HEAD` and `GET` object operations do not return JSON payloads. Their fixtures are JSON envelopes that preserve HTTP status, headers, and body bytes where applicable. `ListObjects` and `ListObjectsV2` fixtures preserve the XML response body inside the same envelope shape so tests can exercise wire-level parsing without making network calls.

Upstream notes:

- `aws`: canonical Amazon S3 response shapes from public S3 API documentation.
- `r2`: Cloudflare R2 S3-compatible API. R2 supports `HeadObject`, `GetObject`, `ListObjects`, and `ListObjectsV2`; ETag headers are quoted on the HTTP wire.
- `b2`: Backblaze B2 S3-compatible API. B2 supports the same S3 calls and may include Backblaze-specific `x-backblaze-*` headers.
- `gcp`: Google Cloud Storage XML API supports object `HEAD` and `GET`. Its bucket listing equivalent is the legacy `GET Bucket` / `ListObjects` call with `prefix`, `marker`, and `max-keys`; public documentation indicates `ListObjectsV2`/`list-type=2` is not supported, so fixtures cover both the successful `ListObjects` path and the `ListObjectsV2` error path.
- `rustfs`: RustFS advertises strict S3 API compatibility, so its fixtures follow normal S3-compatible response shapes with RustFS-specific server/request headers.
