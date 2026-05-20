import type { FileSystemFile } from "@/types/filesystem"

export type MetaOp = "eq" | "neq" | "gte" | "lte" | "gt" | "lt"

export const META_OPS: MetaOp[] = ["eq", "neq", "gte", "lte", "gt", "lt"]

export type MetaFilter = {
  key: string
  op: MetaOp
  value: string
}

export type SearchSort = "name" | "size" | "created_at" | "updated_at"
export type SearchOrder = "asc" | "desc"

export type SearchQuery = {
  q: string
  mimetypes: string[]
  extensions: string[]
  min_size: number | null
  max_size: number | null
  uploaded_by: string | null
  folder_id: string | null
  recursive: boolean
  created_after: string | null
  created_before: string | null
  meta: MetaFilter[]
  sort: SearchSort
  order: SearchOrder
  limit: number
  offset: number
}

export type FileSearchResponse = {
  items: FileSystemFile[]
  total: number
  limit: number
  offset: number
}

export type FacetValue = {
  value: string
  count: number
}

export type Facets = {
  meta_keys: FacetValue[]
  mimetypes: FacetValue[]
  extensions: FacetValue[]
  total: number
}

export const DEFAULT_SEARCH_QUERY: SearchQuery = {
  q: "",
  mimetypes: [],
  extensions: [],
  min_size: null,
  max_size: null,
  uploaded_by: null,
  folder_id: null,
  recursive: false,
  created_after: null,
  created_before: null,
  meta: [],
  sort: "updated_at",
  order: "desc",
  limit: 50,
  offset: 0,
}
