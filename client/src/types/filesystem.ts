export type FolderTreeNode = {
  id: string
  name: string
  parent_id: string | null
  path: string
  effective_permissions: number
  children: FolderTreeNode[]
}

export type Folder = {
  id: string
  parent_id: string | null
  name: string
  path: string
  effective_permissions: number
}

export type FileSystemFile = {
  id: string
  folder_id: string
  blob_id: string
  uploaded_by: string
  uploaded_by_name: string | null
  name: string
  parse_status: number
  meta: FileMeta
  created_at: string
  updated_at: string
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
      kind: "blob"
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
