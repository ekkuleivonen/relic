import {
  DEFAULT_SEARCH_QUERY,
  META_OPS,
  type MetaFilter,
  type MetaOp,
  type SearchOrder,
  type SearchQuery,
  type SearchSort,
} from "@/types/search"

const SORT_VALUES: SearchSort[] = ["name", "size", "created_at", "updated_at"]
const ORDER_VALUES: SearchOrder[] = ["asc", "desc"]

/** Parse the URL search params into a SearchQuery. Unknown / malformed values
 * fall back to the defaults so a stale link can never crash the page. */
export function parseSearchQuery(params: URLSearchParams): SearchQuery {
  return {
    q: params.get("q")?.trim() ?? "",
    mimetypes: dedupe(params.getAll("mimetype")),
    extensions: dedupe(params.getAll("extension")),
    min_size: parseIntOrNull(params.get("min_size")),
    max_size: parseIntOrNull(params.get("max_size")),
    uploaded_by: params.get("uploaded_by") || null,
    folder_id: params.get("folder_id") || null,
    recursive: parseBool(params.get("recursive")),
    created_after: params.get("created_after") || null,
    created_before: params.get("created_before") || null,
    meta: parseMetaFilters(params.getAll("meta")),
    sort: pickEnum(params.get("sort"), SORT_VALUES, DEFAULT_SEARCH_QUERY.sort),
    order: pickEnum(params.get("order"), ORDER_VALUES, DEFAULT_SEARCH_QUERY.order),
    limit: clampInt(params.get("limit"), 1, 200, DEFAULT_SEARCH_QUERY.limit),
    offset: clampInt(params.get("offset"), 0, Number.MAX_SAFE_INTEGER, 0),
  }
}

/** Inverse of parseSearchQuery. Skips defaults so URLs stay short. */
export function serializeSearchQuery(query: SearchQuery): URLSearchParams {
  const params = new URLSearchParams()
  if (query.q) params.set("q", query.q)
  for (const mime of query.mimetypes) params.append("mimetype", mime)
  for (const ext of query.extensions) params.append("extension", ext)
  if (query.min_size !== null) params.set("min_size", String(query.min_size))
  if (query.max_size !== null) params.set("max_size", String(query.max_size))
  if (query.uploaded_by) params.set("uploaded_by", query.uploaded_by)
  if (query.folder_id) params.set("folder_id", query.folder_id)
  if (query.recursive) params.set("recursive", "true")
  if (query.created_after) params.set("created_after", query.created_after)
  if (query.created_before) params.set("created_before", query.created_before)
  for (const metaFilter of query.meta) {
    params.append("meta", `${metaFilter.key}:${metaFilter.op}:${metaFilter.value}`)
  }
  if (query.sort !== DEFAULT_SEARCH_QUERY.sort) params.set("sort", query.sort)
  if (query.order !== DEFAULT_SEARCH_QUERY.order) params.set("order", query.order)
  if (query.limit !== DEFAULT_SEARCH_QUERY.limit) {
    params.set("limit", String(query.limit))
  }
  if (query.offset > 0) params.set("offset", String(query.offset))
  return params
}

/** True when the query has no filters at all (just defaults). */
export function isEmptySearchQuery(query: SearchQuery): boolean {
  return (
    !query.q &&
    query.mimetypes.length === 0 &&
    query.extensions.length === 0 &&
    query.min_size === null &&
    query.max_size === null &&
    query.uploaded_by === null &&
    query.folder_id === null &&
    query.created_after === null &&
    query.created_before === null &&
    query.meta.length === 0
  )
}

/** Number of independent filters active. Used for the pill bar count. */
export function countActiveFilters(query: SearchQuery): number {
  let count = 0
  if (query.q) count += 1
  count += query.mimetypes.length
  count += query.extensions.length
  if (query.min_size !== null) count += 1
  if (query.max_size !== null) count += 1
  if (query.uploaded_by) count += 1
  if (query.folder_id) count += 1
  if (query.created_after) count += 1
  if (query.created_before) count += 1
  count += query.meta.length
  return count
}

/** Toggle a value in a string[] filter (case-insensitive). */
export function toggleStringFilter(
  values: string[],
  candidate: string
): string[] {
  const normalized = candidate.trim()
  if (!normalized) return values
  const lower = normalized.toLowerCase()
  const idx = values.findIndex((value) => value.toLowerCase() === lower)
  if (idx === -1) return [...values, normalized]
  return values.filter((_, i) => i !== idx)
}

/** Build a `/search?...` href from a SearchQuery. */
export function buildSearchHref(query: SearchQuery): string {
  const params = serializeSearchQuery(query)
  const queryString = params.toString()
  return queryString ? `/search?${queryString}` : "/search"
}

/** Build a single-filter `/search?...` href, the common case for chip clicks. */
export function buildSingleFilterHref(
  partial: Partial<SearchQuery>
): string {
  return buildSearchHref({ ...DEFAULT_SEARCH_QUERY, ...partial })
}

function dedupe(values: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of values) {
    const cleaned = raw.trim()
    if (!cleaned) continue
    const key = cleaned.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push(cleaned)
  }
  return out
}

function parseBool(value: string | null): boolean {
  if (!value) return false
  const lower = value.toLowerCase()
  return lower === "true" || lower === "1" || lower === "yes"
}

function parseIntOrNull(value: string | null): number | null {
  if (value === null) return null
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number.parseInt(trimmed, 10)
  if (!Number.isFinite(parsed) || parsed < 0) return null
  return parsed
}

function clampInt(
  value: string | null,
  min: number,
  max: number,
  fallback: number
): number {
  if (value === null) return fallback
  const trimmed = value.trim()
  if (!trimmed) return fallback
  const parsed = Number.parseInt(trimmed, 10)
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(Math.max(parsed, min), max)
}

function pickEnum<T extends string>(
  value: string | null,
  options: T[],
  fallback: T
): T {
  if (value && (options as string[]).includes(value)) {
    return value as T
  }
  return fallback
}

function parseMetaFilters(values: string[]): MetaFilter[] {
  const out: MetaFilter[] = []
  for (const raw of values) {
    const parts = raw.split(":")
    if (parts.length < 3) continue
    const key = parts[0].trim()
    const op = parts[1].trim()
    const value = parts.slice(2).join(":").trim()
    if (!key || !value) continue
    if (!(META_OPS as string[]).includes(op)) continue
    out.push({ key, op: op as MetaOp, value })
  }
  return out
}
