import type { FileMeta } from "@/types/filesystem"
import type { MetaFilter, MetaOp } from "@/types/search"

export type MetaDisplayRow = {
  path: string
  value: unknown
}

export type MetaValueKind = "string" | "number" | "boolean" | "string_list" | "complex"

export type EditableMetaRow = {
  id: string
  path: string
  valueText: string
  kind: MetaValueKind
}

export function isMetaEmpty(meta: FileMeta): boolean {
  return Object.keys(meta).length === 0
}

export function flattenMetaRows(meta: FileMeta, prefix = ""): MetaDisplayRow[] {
  const rows: MetaDisplayRow[] = []
  for (const [rawKey, value] of Object.entries(meta)) {
    const key = rawKey.trim()
    if (!key) continue
    const path = prefix ? `${prefix}.${key}` : key
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      rows.push(...flattenMetaRows(value as FileMeta, path))
      continue
    }
    rows.push({ path, value })
  }
  return rows.sort((a, b) => a.path.localeCompare(b.path))
}

export function formatMetaValue(value: unknown): string {
  if (value === null || value === undefined) return "—"
  if (typeof value === "string") return value
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value)
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return "—"
    return value.map((item) => formatMetaValue(item)).join(", ")
  }
  return JSON.stringify(value)
}

export function metaPreview(
  meta: FileMeta,
  limit = 3
): Array<{ path: string; display: string }> {
  const rows = flattenMetaRows(meta).filter((row) => {
    const value = row.value
    if (value === null || value === undefined) return false
    if (typeof value === "object") return false
    return true
  })
  return rows.slice(0, limit).map((row) => ({
    path: row.path,
    display: formatMetaValue(row.value),
  }))
}

export function buildMetaEqFilter(path: string, value: string): MetaFilter {
  return { key: path, op: "eq", value }
}

export const META_OP_LABELS: Record<MetaOp, string> = {
  eq: "= equals",
  neq: "≠ not equals",
  gt: "> greater than",
  gte: "≥ at least",
  lt: "< less than",
  lte: "≤ at most",
}

export function formatMetaFilter(filter: MetaFilter): string {
  const opLabel = (
    {
      eq: "=",
      neq: "≠",
      gt: ">",
      gte: "≥",
      lt: "<",
      lte: "≤",
    } as const
  )[filter.op]
  return `${filter.key} ${opLabel} ${filter.value}`
}

export function classifyMetaValue(value: unknown): MetaValueKind {
  if (value === null || value === undefined) return "string"
  if (typeof value === "string") return "string"
  if (typeof value === "number") return "number"
  if (typeof value === "boolean") return "boolean"
  if (Array.isArray(value)) {
    if (
      value.every(
        (item) =>
          item === null ||
          item === undefined ||
          typeof item === "string" ||
          typeof item === "number" ||
          typeof item === "boolean"
      )
    ) {
      return "string_list"
    }
    return "complex"
  }
  return "complex"
}

export function valueToEditText(value: unknown, kind: MetaValueKind): string {
  if (kind === "string_list" && Array.isArray(value)) {
    return value.map((item) => String(item ?? "")).join(", ")
  }
  if (value === null || value === undefined) return ""
  return String(value)
}

export function rowsFromMeta(meta: FileMeta): EditableMetaRow[] {
  return flattenMetaRows(meta).map((row) => {
    const kind = classifyMetaValue(row.value)
    return {
      id: row.path,
      path: row.path,
      valueText: kind === "complex" ? formatMetaValue(row.value) : valueToEditText(row.value, kind),
      kind,
    }
  })
}

export function parseMetaPatchJson(raw: string): {
  meta: Record<string, unknown> | null
  error: string | null
} {
  try {
    const parsed = JSON.parse(raw) as unknown
    if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
      return { meta: null, error: "Metadata must be a JSON object" }
    }
    return { meta: parsed as Record<string, unknown>, error: null }
  } catch (error) {
    return {
      meta: null,
      error: error instanceof Error ? error.message : "Invalid JSON metadata",
    }
  }
}

export function parseRowValue(
  valueText: string,
  kind: MetaValueKind
): unknown | null {
  const trimmed = valueText.trim()
  if (kind === "string_list") {
    if (!trimmed) return []
    return trimmed.split(",").map((part) => part.trim()).filter(Boolean)
  }
  if (kind === "number") {
    if (!trimmed) return null
    const parsed = Number(trimmed)
    if (!Number.isFinite(parsed)) return null
    return parsed
  }
  if (kind === "boolean") {
    if (trimmed === "true") return true
    if (trimmed === "false") return false
    return null
  }
  return trimmed
}

export function valuesEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

export function getMetaValueAtPath(meta: FileMeta, path: string): unknown {
  let current: unknown = meta
  for (const part of path.split(".")) {
    if (
      current === null ||
      current === undefined ||
      typeof current !== "object" ||
      Array.isArray(current)
    ) {
      return undefined
    }
    current = (current as Record<string, unknown>)[part]
  }
  return current
}

export function setMetaByPath(
  target: Record<string, unknown>,
  path: string,
  value: unknown
): void {
  const parts = path.split(".").filter(Boolean)
  if (parts.length === 0) return
  let current: Record<string, unknown> = target
  for (let index = 0; index < parts.length - 1; index += 1) {
    const part = parts[index]
    const next = current[part]
    if (
      next === null ||
      next === undefined ||
      typeof next !== "object" ||
      Array.isArray(next)
    ) {
      current[part] = {}
    }
    current = current[part] as Record<string, unknown>
  }
  current[parts[parts.length - 1]] = value
}

export function buildMetaPatchFromRows(
  meta: FileMeta,
  rows: EditableMetaRow[]
): Record<string, unknown> {
  const patch: Record<string, unknown> = {}
  for (const row of rows) {
    const path = row.path.trim()
    if (!path || row.kind === "complex") continue
    const parsed = parseRowValue(row.valueText, row.kind)
    if (parsed === null && row.kind !== "string") continue
    const previous = getMetaValueAtPath(meta, path)
    const nextValue = row.kind === "string" ? row.valueText : parsed
    if (valuesEqual(previous, nextValue)) continue
    setMetaByPath(patch, path, nextValue as unknown)
  }
  return patch
}

export const META_PATCH_HINT =
  "Saves merge into existing metadata. Keys not in the patch are kept. Removing a key here does not delete it on the server."
