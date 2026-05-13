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
  /** Local override; null means inherit (admin API). */
  cooldown_days?: number | null
  min_tier?: number | null
  /** Resolved from this folder or ancestors (admin API). */
  effective_min_tier?: number | null
  effective_cooldown_days?: number | null
  children: FolderTreeNode[]
}

export type Folder = {
  id: string
  parent_id: string | null
  name: string
  path: string
  effective_permissions: number
  cooldown_days?: number | null
  min_tier?: number | null
  effective_min_tier?: number | null
  effective_cooldown_days?: number | null
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
