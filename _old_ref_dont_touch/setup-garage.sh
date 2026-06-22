#!/bin/bash
set -euo pipefail

HOT_CONTAINER="${HOT_CONTAINER:-relic_garage_hot}"
COLD_CONTAINER="${COLD_CONTAINER:-relic_garage_cold}"
ZONE="${GARAGE_ZONE:-dc1}"
CAPACITY="${GARAGE_CAPACITY:-4G}"
LAKE_BUCKET="${LAKE_BUCKET:-lake}"
BLOB_BUCKET="${BLOB_BUCKET:-blobs}"

HOT_KEY_NAME="${GARAGE_HOT_KEY_NAME:-relic-hot-app}"
COLD_KEY_NAME="${GARAGE_COLD_KEY_NAME:-relic-cold-app}"

garage_exec() {
  local container="$1"
  shift
  docker exec "$container" /garage "$@"
}

extract_field() {
  local text="$1"
  local field="$2"
  printf '%s\n' "$text" | awk -F': ' -v field="$field" '$1 == field { print $2 }'
}

wait_for_garage() {
  local container="$1"
  echo "Waiting for $container..."
  until garage_exec "$container" status >/dev/null 2>&1; do
    sleep 1
  done
}

bootstrap_node() {
  local container="$1"
  local full_id node_id next_version

  echo "Bootstrapping $container..."
  full_id="$(garage_exec "$container" node id -q)"
  node_id="${full_id%%@*}"
  echo "Node ID: $node_id"

  echo "Assigning layout for $container..."
  garage_exec "$container" layout assign -z "$ZONE" -c "$CAPACITY" "$node_id" || true

  echo "Applying layout for $container..."
  next_version="$(
    garage_exec "$container" layout show 2>&1 \
      | grep -o 'apply --version [0-9][0-9]*' \
      | awk '{ print $3 }' \
      | tail -n 1
  )"
  next_version="${next_version:-1}"
  garage_exec "$container" layout apply --version "$next_version" \
    || echo "Layout already applied or no changes needed"
}

ensure_bucket() {
  local container="$1"
  local bucket="$2"

  if garage_exec "$container" bucket info "$bucket" >/dev/null 2>&1; then
    echo "Bucket already exists on $container: $bucket"
    return
  fi

  echo "Creating bucket on $container: $bucket"
  garage_exec "$container" bucket create "$bucket" >/dev/null
}

ensure_key() {
  local container="$1"
  local key_name="$2"
  local access_var="$3"
  local secret_var="$4"
  local create_out key_id secret_key existing_id

  if garage_exec "$container" key info "$key_name" >/dev/null 2>&1; then
    existing_id="$(extract_field "$(garage_exec "$container" key info "$key_name")" "Key ID")"
    if [[ -n "${!access_var:-}" && -n "${!secret_var:-}" ]]; then
      if [[ -n "$existing_id" && "${!access_var}" != "$existing_id" ]]; then
        echo "Stored $access_var does not match existing Garage key '$key_name' on $container." >&2
        exit 1
      fi
      echo "Key already exists on $container: $key_name"
      return
    fi

    echo "Key '$key_name' already exists on $container, but its secret is not recoverable." >&2
    exit 1
  fi

  echo "Creating key on $container: $key_name"
  create_out="$(garage_exec "$container" key create "$key_name")"
  key_id="$(extract_field "$create_out" "Key ID")"
  secret_key="$(extract_field "$create_out" "Secret key")"

  if [[ -z "$key_id" || -z "$secret_key" ]]; then
    echo "Failed to parse key credentials for $key_name on $container" >&2
    printf '%s\n' "$create_out" >&2
    exit 1
  fi

  printf -v "$access_var" '%s' "$key_id"
  printf -v "$secret_var" '%s' "$secret_key"
}

allow_key_on_bucket() {
  local container="$1"
  local bucket="$2"
  local key_name="$3"

  echo "Granting $key_name access to $bucket on $container"
  garage_exec "$container" bucket allow \
    --read \
    --write \
    --owner \
    "$bucket" \
    --key "$key_name" >/dev/null
}

print_env_block() {
  cat <<EOF
S3_HOT_ACCESS_KEY="${S3_HOT_ACCESS_KEY}"
S3_HOT_SECRET_KEY="${S3_HOT_SECRET_KEY}"
S3_HOT_ENDPOINT=http://localhost:3900
S3_HOT_REGION=garage

S3_COLD_ACCESS_KEY="${S3_COLD_ACCESS_KEY}"
S3_COLD_SECRET_KEY="${S3_COLD_SECRET_KEY}"
S3_COLD_ENDPOINT=http://localhost:3910
S3_COLD_REGION=garage

S3_LAKE_BUCKET=${LAKE_BUCKET}
S3_BLOB_BUCKET=${BLOB_BUCKET}
EOF
}



wait_for_garage "$HOT_CONTAINER"
bootstrap_node "$HOT_CONTAINER"

wait_for_garage "$COLD_CONTAINER"
bootstrap_node "$COLD_CONTAINER"

ensure_key "$HOT_CONTAINER" "$HOT_KEY_NAME" S3_HOT_ACCESS_KEY S3_HOT_SECRET_KEY
ensure_key "$COLD_CONTAINER" "$COLD_KEY_NAME" S3_COLD_ACCESS_KEY S3_COLD_SECRET_KEY

for bucket in "$LAKE_BUCKET" "$BLOB_BUCKET"; do
  ensure_bucket "$HOT_CONTAINER" "$bucket"
  ensure_bucket "$COLD_CONTAINER" "$bucket"
  allow_key_on_bucket "$HOT_CONTAINER" "$bucket" "$HOT_KEY_NAME"
  allow_key_on_bucket "$COLD_CONTAINER" "$bucket" "$COLD_KEY_NAME"
done

echo
echo "Done!"
echo
echo "Hot S3 API: http://localhost:3900"
echo "WebUI (hot): http://localhost:3909"
echo
echo "Cold S3 API: http://localhost:3910"
echo "WebUI (cold): http://localhost:3919"
echo
echo "Paste this into .env:"
print_env_block
