export type FilesystemEventRecord = {
  id: string
  seq: number
  event_type: string
  created_at: string
  file_id: string | null
  folder_id: string
  actor_id: string | null
  request_id: string | null
  payload: Record<string, unknown>
}

export type FilesystemEventsQuery = {
  after?: number
  folder_id?: string
  recursive?: boolean
  types?: string[]
  limit?: number
}

export type FilesystemEventsResponse = {
  items: FilesystemEventRecord[]
  cursor: number | null
  has_more: boolean
  oldest_seq: number | null
}

export const FILESYSTEM_EVENT_TYPES = [
  "file.created",
  "file.content_updated",
  "file.meta_updated",
  "file.renamed",
  "file.moved",
  "file.deleted",
  "folder.created",
  "folder.renamed",
  "folder.moved",
  "folder.deleted",
  "folder.duplicated",
] as const
