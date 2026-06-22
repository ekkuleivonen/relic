import type {
  StorageBackendCreateInput,
  StorageBackendKind,
} from "@/types/storage-backends"

type StorageBackendFormFields = {
  name: string
  endpoint: string
  region: string
  namespace: string
  key_id: string
  secret_access_key: string
  kind: StorageBackendKind
}

export function buildStorageBackendCreatePayload(
  values: StorageBackendFormFields,
  max_size_bytes: number
): StorageBackendCreateInput {
  if (values.kind === "filesystem") {
    return {
      name: values.name,
      endpoint: values.endpoint,
      namespace: values.namespace,
      max_size_bytes,
      kind: "filesystem",
    }
  }

  return {
    name: values.name,
    endpoint: values.endpoint,
    region: values.region,
    namespace: values.namespace,
    key_id: values.key_id,
    secret_access_key: values.secret_access_key,
    max_size_bytes,
    kind: "s3",
  }
}

export function storageBackendKindLabel(kind: StorageBackendKind): string {
  switch (kind) {
    case "filesystem":
      return "Filesystem"
    case "azure_blob":
      return "Azure Blob"
    case "gcs":
      return "GCS"
    default:
      return "S3"
  }
}
