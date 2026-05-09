export type FolderTreeNode = {
  id: string
  name: string
  parent_id: string | null
  children: FolderTreeNode[]
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
    }
  | {
      kind: "blob"
      id: string
      name: string
      size?: number
      mime_type?: string
      updated_at: string
    }
