# Upstream Object Notification Fixtures

Raw notification payloads from object storage providers. Each fixture is a JSON envelope with metadata plus the wire-format `body` Relic receives (direct webhook, SNS wrapper, or Pub/Sub push).

Fixture keys use the same bucket (`relic-fixtures`) and object keys (`photos/a.jpg`) as `packages/upstreams/s3compat/testdata/mocks/` where applicable.

| Upstream | Transport | Created format | Removed format |
| --- | --- | --- | --- |
| `aws` | S3 event notification (`Records`) | `aws_object_created.json` | `aws_object_removed.json` |
| `aws` | SNS wrapping S3 `Records` | `aws_sns_object_created.json` | — |
| `aws` | EventBridge | `aws_eventbridge_object_created.json` | — |
| `b2` | Native B2 webhook (`events[]`) | `b2_object_created.json` | `b2_object_removed.json` |
| `gcp` | Pub/Sub push HTTP (`message.attributes` + base64 `data`) | `gcp_object_created.json` | `gcp_object_removed.json` |
| `r2` | Cloudflare R2 queue message | `r2_object_created.json` | `r2_object_removed.json` |
| `rustfs` | S3-compatible webhook (`Records`, `eventSource: rustfs:s3`) | `rustfs_object_created.json` | `rustfs_object_removed.json` |

The consumer maps normalized events to **`import_objects`** (create/overwrite) and **`remove_objects`** (delete) only. Tag and metadata-only notifications are ignored; those changes are picked up on the next import/refresh via `FetchCatalogAttributes` or by `sync_bucket` / `scan_bucket`.

Sources:

- AWS S3: https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html
- AWS EventBridge: https://docs.aws.amazon.com/AmazonS3/latest/userguide/ev-events.html
- Backblaze B2: https://www.backblaze.com/docs/cloud-storage-event-notifications-reference-guide
- Cloudflare R2: https://developers.cloudflare.com/r2/buckets/event-notifications/
- Google Cloud Storage: https://cloud.google.com/storage/docs/pubsub-notifications
- RustFS: https://github.com/rustfs/rustfs (S3-compatible bucket notifications, `eventSource: rustfs:s3`)
