import type { SearchAttribute } from "@/types/search"

export const DEFAULT_PITHOSYSQL_QUERY = `FROM objects
LIMIT 100`

export const BUILTIN_SEARCH_ATTRIBUTES: SearchAttribute[] = [
  { path: "upstream.size", type: "integer", source: "builtin" },
  { path: "upstream.last_modified", type: "timestamp", source: "builtin" },
  { path: "upstream.header.content_type", type: "string", source: "builtin" },
  { path: "upstream.s3.version_id", type: "string", source: "builtin" },
  { path: "core.first_seen_at", type: "timestamp", source: "builtin" },
  { path: "core.last_seen_at", type: "timestamp", source: "builtin" },
  { path: "core.object_id", type: "string", source: "builtin" },
]

export const BUILTIN_RELATION_TYPES = ["duplicate"] as const

export const RELATION_DIRECTIONS = ["any", "in", "out"] as const
