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
  name: string
  meta: {
    file_size?: number
    mime_type?: string
    extension?: string
    original_name?: string
    [key: string]: unknown
  }
  created_at: string
  updated_at: string
  accessed_at: string
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
    }

export type PresignUploadRequest = {
  folder_id: string
  filename: string
  file_size: number
  mime_type: string | null
  meta: Record<string, string>
}

export type PresignUploadResponse = {
  url: string
  headers: Record<string, string>
  expires_at: string
}
