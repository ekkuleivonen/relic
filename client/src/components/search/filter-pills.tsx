import { X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { formatMetaFilter } from "@/lib/file-meta"
import { formatBytes } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { SearchQuery } from "@/types/search"

type FilterPillsProps = {
  query: SearchQuery
  scopeLabel?: string | null
  onChange: (next: SearchQuery) => void
  onClearAll: () => void
  className?: string
}

export function FilterPills({
  query,
  scopeLabel,
  onChange,
  onClearAll,
  className,
}: FilterPillsProps) {
  const pills = collectPills(query, scopeLabel)
  if (pills.length === 0) return null

  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-1.5 text-xs",
        className
      )}
    >
      {pills.map((pill) => (
        <Pill
          key={pill.key}
          label={pill.label}
          tone={pill.tone}
          onRemove={() => onChange(pill.remove(query))}
        />
      ))}
      <Button
        type="button"
        variant="ghost"
        size="xs"
        className="ml-1 text-muted-foreground hover:text-foreground"
        onClick={onClearAll}
      >
        Clear all
      </Button>
    </div>
  )
}

type PillTone = "meta" | "type" | "scope" | "size" | "q" | "date" | "user"

type PillSpec = {
  key: string
  label: string
  tone: PillTone
  remove: (query: SearchQuery) => SearchQuery
}

function Pill({
  label,
  tone,
  onRemove,
}: {
  label: string
  tone: PillTone
  onRemove: () => void
}) {
  return (
    <span
      data-tone={tone}
      className={cn(
        "inline-flex h-6 items-center gap-1 rounded-full border pl-2 pr-1 font-medium",
        toneClasses(tone)
      )}
    >
      <span className="truncate max-w-[20rem]">{label}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove filter ${label}`}
        className="inline-flex size-4 items-center justify-center rounded-full text-muted-foreground hover:bg-muted-foreground/10 hover:text-foreground"
      >
        <X className="size-3" />
      </button>
    </span>
  )
}

function toneClasses(tone: PillTone) {
  switch (tone) {
    case "type":
      return "border-blue-500/20 bg-blue-500/10 text-blue-600 dark:text-blue-300"
    case "scope":
      return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300"
    case "size":
    case "meta":
      return "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
    case "date":
      return "border-violet-500/20 bg-violet-500/10 text-violet-700 dark:text-violet-300"
    case "q":
      return "border-foreground/20 bg-foreground/10 text-foreground"
    case "user":
    default:
      return "border-muted-foreground/20 bg-muted text-foreground"
  }
}

function collectPills(
  query: SearchQuery,
  scopeLabel: string | null | undefined
): PillSpec[] {
  const pills: PillSpec[] = []

  if (query.q) {
    pills.push({
      key: "q",
      tone: "q",
      label: `“${query.q}”`,
      remove: (q) => ({ ...q, q: "", offset: 0 }),
    })
  }

  if (query.folder_id) {
    pills.push({
      key: "scope",
      tone: "scope",
      label: scopeLabel
        ? `In ${scopeLabel}${query.recursive ? " (recursive)" : ""}`
        : `Scoped to folder${query.recursive ? " (recursive)" : ""}`,
      remove: (q) => ({ ...q, folder_id: null, recursive: false, offset: 0 }),
    })
  }

  for (const mime of query.mimetypes) {
    pills.push({
      key: `mime:${mime}`,
      tone: "type",
      label: `MIME: ${mime}`,
      remove: (q) => ({
        ...q,
        mimetypes: q.mimetypes.filter((value) => value !== mime),
        offset: 0,
      }),
    })
  }

  for (const ext of query.extensions) {
    pills.push({
      key: `ext:${ext}`,
      tone: "type",
      label: `.${ext}`,
      remove: (q) => ({
        ...q,
        extensions: q.extensions.filter((value) => value !== ext),
        offset: 0,
      }),
    })
  }

  if (query.min_size !== null || query.max_size !== null) {
    const min = query.min_size !== null ? formatBytes(query.min_size) : "0"
    const max = query.max_size !== null ? formatBytes(query.max_size) : "∞"
    pills.push({
      key: "size",
      tone: "size",
      label: `Size: ${min} – ${max}`,
      remove: (q) => ({ ...q, min_size: null, max_size: null, offset: 0 }),
    })
  }

  if (query.created_after || query.created_before) {
    const after = query.created_after?.slice(0, 10) ?? ""
    const before = query.created_before?.slice(0, 10) ?? ""
    pills.push({
      key: "date",
      tone: "date",
      label: `Created: ${after || "—"} → ${before || "—"}`,
      remove: (q) => ({
        ...q,
        created_after: null,
        created_before: null,
        offset: 0,
      }),
    })
  }

  if (query.uploaded_by) {
    pills.push({
      key: "uploader",
      tone: "user",
      label: `Uploader: ${query.uploaded_by.slice(0, 8)}…`,
      remove: (q) => ({ ...q, uploaded_by: null, offset: 0 }),
    })
  }

  for (const metaFilter of query.meta) {
    pills.push({
      key: `meta:${metaFilter.key}:${metaFilter.op}:${metaFilter.value}`,
      tone: "meta",
      label: formatMetaFilter(metaFilter),
      remove: (q) => ({
        ...q,
        meta: q.meta.filter(
          (other) =>
            other.key !== metaFilter.key ||
            other.op !== metaFilter.op ||
            other.value !== metaFilter.value
        ),
        offset: 0,
      }),
    })
  }

  return pills
}
