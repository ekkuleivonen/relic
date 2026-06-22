# Mounting Relic with rclone

Relic exposes an S3-compatible gateway at `/s3`. You can mount it on macOS with
[rclone](https://rclone.org/) and browse or edit files in Finder like a normal
folder.

## Prerequisites

- **rclone** — `brew install rclone`
- **Relic running** with the S3 gateway reachable (e.g. `http://localhost:8000/s3`
  for local Docker dev, or your production host)
- A **Relic access key** (Admin UI → Access Keys). You need the key ID (`RK…`)
  and secret (shown once at creation).

Access keys created before native S3 auth may need to be **reissued** before
they work with rclone or other SigV4 clients.

## Configure the remote

Replace the placeholders with your credentials and endpoint.

**Local dev:**

```bash
rclone config create relic s3 \
  provider Other \
  access_key_id "RK..." \
  secret_access_key "YOUR_SECRET" \
  region relic \
  endpoint "http://localhost:8000/s3" \
  force_path_style true \
  sign_accept_encoding false \
  list_version 2 \
  no_check_bucket true
```

**Production:** use your host, e.g. `https://relic.example.com/s3`.

| Setting | Value |
|---------|-------|
| Remote name | `relic` (your choice) |
| Provider | Other (S3-compatible) |
| Region | `relic` (`RELIC_SIGNING_REGION`) |
| Bucket | `relic` (`RELIC_GATEWAY_BUCKET`) |
| Path style | `true` (required) |
| Endpoint | `{base_url}/s3` |
| `sign_accept_encoding` | `false` (required for rclone) |
| `list_version` | `2` (Relic only supports ListObjectsV2) |
| `no_check_bucket` | `true` (skip ListBuckets; rclone cannot list buckets reliably) |

Relic uses a fixed virtual bucket (`relic` by default). Folder paths live in
object keys (e.g. `Uploads/2024/photo.jpg`).

## Test the connection

```bash
# List top-level folders in the bucket
rclone lsf relic:relic
```

Verify Relic is up:

```bash
curl -s http://localhost:8000/healthz
```

## Mount

Create a mount point (once):

```bash
mkdir -p ~/Relic
```

On macOS, prefer **`nfsmount`** — it uses rclone’s built-in NFS server and does
not require macFUSE or FUSE-T:

```bash
rclone nfsmount relic:relic ~/Relic \
  --vfs-cache-mode writes \
  --daemon \
  --daemon-wait 30s
```

- **`--vfs-cache-mode writes`** — required for read/write on macOS; without it
  the mount is read-only.
- **`--daemon`** — runs in the background.

Mount a specific folder only:

```bash
rclone nfsmount relic:relic/Uploads ~/Relic \
  --vfs-cache-mode writes \
  --daemon
```

## Unmount

```bash
umount ~/Relic
```

If that fails:

```bash
diskutil unmount ~/Relic
```

Stop the background daemon if needed:

```bash
pkill -f "rclone nfsmount relic:relic"
```

## Troubleshooting

### `SignatureDoesNotMatch`

rclone signs the `Accept-Encoding` header by default. Relic’s SigV4 verifier
does not accept that, so requests fail with `SignatureDoesNotMatch` even when
credentials and endpoint are correct.

Fix — add to the remote config (or pass as flags):

```bash
rclone config update relic \
  sign_accept_encoding false \
  list_version 2 \
  no_check_bucket true
```

Verify:

```bash
rclone lsf relic:relic
```

(`rclone lsd relic:` may still fail — use `lsf relic:relic` or mount directly instead.)

Debug with request dumps:

```bash
rclone lsd relic: --dump headers -vv
```

Look for `Accept-Encoding` in `SignedHeaders` inside the `Authorization` header.
It should not appear after the fix.

### `InvalidRequest: Only ListObjectsV2 ...`

Relic does not support legacy ListObjects v1. Set `list_version = 2` on the
remote (see above).

## Notes

- Relic’s S3 gateway implements a subset of S3 (PutObject, GetObject,
  ListObjectsV2, multipart, etc.). Some rclone operations may not work — see
  `HAZARD_LOG.md` (H-015).
- Folder names with spaces are supported; use path-style addressing (already
  set via `force_path_style`).
- For metadata (rename, move, permissions), use the Relic API/UI. rclone mounts
  the **bytes** layer only.

## Optional: mount at login

Wrap the `nfsmount` command in a macOS LaunchAgent if you want the mount to
start automatically when you log in.
