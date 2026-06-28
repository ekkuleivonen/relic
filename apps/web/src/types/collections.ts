import type { SearchDependency } from "@/types/search"

export type CollectionStatus = "valid" | "invalid"

export type Collection = {
  id: string
  name: string
  description: string
  query: string
  query_version: string
  dependencies: SearchDependency[]
  status: CollectionStatus
  owner_user_id?: string
  created_by_type?: string
  created_by_id?: string
  created_at: string
  updated_at: string
}

export type ListCollectionsResponse = {
  collections: Collection[]
}

export type ListCollectionObjectsResponse = {
  objects: import("@/types/objects").CatalogObject[]
}

export type CreateCollectionInput = {
  name: string
  description?: string
  query: string
}

export type UpdateCollectionInput = {
  name?: string
  description?: string
  query?: string
}
