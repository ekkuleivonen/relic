import type { CatalogObject } from "@/types/objects"

export type SearchDependencyKind = "target" | "field" | "attribute" | "relation" | "bucket"

export type SearchDependency = {
  kind: SearchDependencyKind
  name: string
  type?: string
}

export type SearchAttribute = {
  path: string
  type?: string
  source?: string
}

export type ListSearchAttributesResponse = {
  attributes: SearchAttribute[]
}

export type ListSearchRelationTypesResponse = {
  relation_types: string[]
}

export type ValidateSearchResponse = {
  query: string
  query_version: string
  from: string
  dependencies: SearchDependency[]
}

export type ExecuteSearchRequest = {
  query: string
  bucket_id?: string
}

export type ExecuteSearchResponse = {
  objects: CatalogObject[]
}
