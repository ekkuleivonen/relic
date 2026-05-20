export type FolderContentsSortKey = "name" | "type" | "size" | "updated"
export type FolderContentsSortDir = "asc" | "desc"
export type FolderContentsSortState = {
  key: FolderContentsSortKey
  dir: FolderContentsSortDir
}

export type FolderTreeNode = {
  id: string
  name: string
  parent_id: string | null
  path: string
  effective_permissions: number
  preferred_bucket_id?: string | null
  effective_preferred_bucket_id?: string | null
  children: FolderTreeNode[]
}

export type Folder = {
  id: string
  parent_id: string | null
  name: string
  path: string
  effective_permissions: number
  preferred_bucket_id?: string | null
  effective_preferred_bucket_id?: string | null
}

/** Opaque consumer-owned metadata; shape is not enforced by Relic. */
export type FileMeta = Record<string, unknown>

export type FileSystemFile = {
  id: string
  folder_id: string
  blob_id: string
  actor_id: string
  actor_name: string | null
  name: string
  meta: FileMeta
  size_bytes: number
  mimetype: string
  extension: string
  created_at: string
  updated_at: string
}

export type PaginatedFilesResponse = {
  items: FileSystemFile[]
  total: number
  limit: number
  offset: number
}

export type BulkFileMutationError = {
  file_id: string
  code: string
  message: string
}

export type BulkDeleteFilesResponse = {
  deleted_ids: string[]
  errors: BulkFileMutationError[]
}

export type BulkMoveFilesResponse = {
  moved_ids: string[]
  errors: BulkFileMutationError[]
}

export type BulkPatchFileMetaResponse = {
  patched_ids: string[]
  errors: BulkFileMutationError[]
}

export type FileSystemEntry =
  | {
      kind: "folder"
      id: string
      name: string
      href: string
      updated_at?: string
      child_count: number
      node: FolderTreeNode
    }
  | {
      kind: "file"
      id: string
      name: string
      size?: number
      mime_type?: string
      updated_at: string
      file: FileSystemFile
      folder: FolderTreeNode
    }

export type PresignUploadRequest = {
  folder_id: string
  filename: string
  meta: Record<string, string>
}

export type PresignUploadResponse = {
  url: string
  headers: Record<string, string>
  expires_at?: string
}

export type FolderStats = {
  folder_id: string
  file_count: number
  enriched_file_count: number
  logical_size_bytes: number
  enrichment_coverage: number | null
}

export type FolderContentsRow =
  | {
      kind: "folder"
      folder: Folder
    }
  | {
      kind: "file"
      file: FileSystemFile
    }

export function metaStringList(meta: FileMeta, key: string): string[] {
  const value = meta[key]
  if (!Array.isArray(value)) {
    return []
  }
  return value.filter((item): item is string => typeof item === "string")
}

export function metaString(meta: FileMeta, key: string): string | null {
  const value = meta[key]
  return typeof value === "string" && value.trim() ? value : null
}

export function metaKvs(meta: FileMeta): Record<string, string | number | boolean | null> {
  const value = meta.kvs
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {}
  }
  return value as Record<string, string | number | boolean | null>
}
