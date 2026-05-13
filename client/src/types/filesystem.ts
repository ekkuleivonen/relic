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
  /** Local override; null means inherit from ancestor (admin API). */
  preferred_bucket_id?: string | null
  /** Resolved from this folder or ancestors (admin API). */
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

export type FileMeta = {
  schema_version: string
  size: number
  extension: string
  mimetype: string
  original_filename: string
  tags: string[]
  keywords: string[]
  summary: string | null
  kvs: Record<string, string | number | boolean | null>
}

export type FileSystemFile = {
  id: string
  folder_id: string
  blob_id: string
  uploaded_by: string
  uploaded_by_name: string | null
  name: string
  meta_extract_status: number
  meta: FileMeta
  created_at: string
  updated_at: string
}

export type PaginatedFilesResponse = {
  items: FileSystemFile[]
  total: number
  limit: number
  offset: number
}

/**
 * Recursive rollup over a folder + descendants.
 *
 * `enrichment_coverage` is `null` when the subtree has no files (avoid 0/0).
 * `logical_size_bytes` sums each File row's blob size — duplicates count
 * once per reference, not once per blob.
 */
export type FolderStats = {
  folder_id: string
  file_count: number
  enriched_file_count: number
  logical_size_bytes: number
  enrichment_coverage: number | null
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
  expires_at: string
}
