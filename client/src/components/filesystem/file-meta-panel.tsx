import * as React from "react"
import { Braces, Copy, ListTree, Pencil } from "lucide-react"
import { Link } from "react-router"
import { toast } from "sonner"

import { MetaJsonEditor } from "@/components/filesystem/meta-json-editor"
import { MetaSimpleEditor } from "@/components/filesystem/meta-simple-editor"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { usePatchFileMeta } from "@/hooks/use-files"
import {
  META_PATCH_HINT,
  buildMetaPatchFromRows,
  flattenMetaRows,
  formatMetaValue,
  isMetaEmpty,
  parseMetaPatchJson,
  rowsFromMeta,
  type EditableMetaRow,
} from "@/lib/file-meta"
import { buildSingleFilterHref } from "@/lib/search-query"
import { cn } from "@/lib/utils"
import type { FileMeta } from "@/types/filesystem"

type FileMetaPanelProps = {
  meta: FileMeta
  fileId?: string
  canEdit?: boolean
  className?: string
}

export function FileMetaPanel({
  meta,
  fileId,
  canEdit = false,
  className,
}: FileMetaPanelProps) {
  const patchMeta = usePatchFileMeta()
  const [editing, setEditing] = React.useState(false)
  const [editMode, setEditMode] = React.useState<"simple" | "json">("simple")
  const [view, setView] = React.useState<"tree" | "json">("tree")
  const [draftRows, setDraftRows] = React.useState<EditableMetaRow[]>([])
  const [jsonDraft, setJsonDraft] = React.useState("{}")
  const [jsonError, setJsonError] = React.useState<string | null>(null)

  const rows = React.useMemo(() => flattenMetaRows(meta), [meta])
  const json = React.useMemo(() => JSON.stringify(meta, null, 2), [meta])

  function beginEdit(mode: "simple" | "json" = "simple") {
    setDraftRows(rowsFromMeta(meta))
    setJsonDraft("{}")
    setJsonError(null)
    setEditMode(mode)
    setEditing(true)
  }

  function cancelEdit() {
    setEditing(false)
    setJsonError(null)
  }

  async function saveSimple() {
    if (!fileId) return
    const patch = buildMetaPatchFromRows(meta, draftRows)
    if (Object.keys(patch).length === 0) {
      toast.message("No metadata changes to save")
      setEditing(false)
      return
    }
    try {
      await patchMeta.mutateAsync({ file_id: fileId, meta: patch })
      setEditing(false)
    } catch {
      // hook toasts
    }
  }

  async function saveJson() {
    if (!fileId) return
    const { meta: patch, error } = parseMetaPatchJson(jsonDraft)
    if (error || !patch) {
      setJsonError(error)
      return
    }
    if (Object.keys(patch).length === 0) {
      toast.message("Patch object is empty")
      return
    }
    try {
      await patchMeta.mutateAsync({ file_id: fileId, meta: patch })
      setEditing(false)
    } catch {
      // hook toasts
    }
  }

  if (editing) {
    return (
      <div className={cn("space-y-4", className)}>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex gap-1">
            <Button
              type="button"
              size="xs"
              variant={editMode === "simple" ? "secondary" : "ghost"}
              onClick={() => setEditMode("simple")}
            >
              Fields
            </Button>
            <Button
              type="button"
              size="xs"
              variant={editMode === "json" ? "secondary" : "ghost"}
              onClick={() => setEditMode("json")}
            >
              <Braces className="size-3.5" />
              JSON
            </Button>
          </div>
        </div>

        {editMode === "simple" ? (
          <MetaSimpleEditor
            rows={draftRows}
            onChange={setDraftRows}
            onOpenJson={() => setEditMode("json")}
          />
        ) : (
          <MetaJsonEditor
            value={jsonDraft}
            onChange={setJsonDraft}
            id="file-meta-patch-json"
            label="Metadata patch"
            description="JSON object to deep-merge. Only include keys you want to add or update."
            rows={12}
            error={jsonError}
            onErrorChange={setJsonError}
          />
        )}

        <p className="text-xs text-muted-foreground">{META_PATCH_HINT}</p>

        <div className="flex flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={cancelEdit}
            disabled={patchMeta.isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={() =>
              void (editMode === "simple" ? saveSimple() : saveJson())
            }
            disabled={patchMeta.isPending}
          >
            {patchMeta.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    )
  }

  if (isMetaEmpty(meta)) {
    return (
      <div className={cn("space-y-3", className)}>
        <p className="text-sm text-muted-foreground">
          No metadata yet.
          {canEdit && fileId
            ? " Add fields below or set via API."
            : " Set fields via API."}
        </p>
        {canEdit && fileId ? (
          <Button type="button" variant="outline" size="sm" onClick={() => beginEdit()}>
            <Pencil className="size-3.5" />
            Add metadata
          </Button>
        ) : (
          <code className="block rounded bg-muted px-2 py-1 text-xs">
            PATCH /api/files/&#123;id&#125;/meta
          </code>
        )}
      </div>
    )
  }

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline">{rows.length} fields</Badge>
        <div className="ml-auto flex gap-1">
          {canEdit && fileId ? (
            <Button
              type="button"
              size="xs"
              variant="outline"
              onClick={() => beginEdit()}
            >
              <Pencil className="size-3.5" />
              Edit
            </Button>
          ) : null}
          <Button
            type="button"
            size="xs"
            variant={view === "tree" ? "secondary" : "ghost"}
            onClick={() => setView("tree")}
          >
            <ListTree className="size-3.5" />
            Tree
          </Button>
          <Button
            type="button"
            size="xs"
            variant={view === "json" ? "secondary" : "ghost"}
            onClick={() => setView("json")}
          >
            <Braces className="size-3.5" />
            JSON
          </Button>
        </div>
      </div>

      {view === "json" ? (
        <div className="relative">
          <pre className="max-h-96 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-xs">
            {json}
          </pre>
          <Button
            type="button"
            size="icon-sm"
            variant="outline"
            className="absolute right-2 top-2"
            aria-label="Copy metadata JSON"
            onClick={() => void copyText(json)}
          >
            <Copy className="size-3.5" />
          </Button>
        </div>
      ) : (
        <div className="divide-y rounded-md border">
          {rows.map((row) => (
            <MetaRow key={row.path} path={row.path} value={row.value} />
          ))}
        </div>
      )}
    </div>
  )
}

function MetaRow({ path, value }: { path: string; value: unknown }) {
  const filterHref = scalarFilterHref(path, value)

  return (
    <div className="grid gap-1 px-3 py-2 text-sm sm:grid-cols-[12rem_1fr] sm:gap-4">
      <div className="font-medium text-muted-foreground">{path}</div>
      <div className="break-words">
        {Array.isArray(value) ? (
          <div className="flex flex-wrap gap-1.5">
            {value.map((item, index) => {
              const chipHref = scalarFilterHref(path, item)
              const label = formatMetaValue(item)
              if (chipHref) {
                return (
                  <Link
                    key={`${path}-${index}`}
                    to={chipHref}
                    title={`Find files where ${path} matches`}
                    className="rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary hover:border-primary/40"
                  >
                    {label}
                  </Link>
                )
              }
              return (
                <span
                  key={`${path}-${index}`}
                  className="rounded-full border border-muted-foreground/20 bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground"
                >
                  {label}
                </span>
              )
            })}
          </div>
        ) : filterHref ? (
          <Link
            to={filterHref}
            title={`Find files where ${path} matches`}
            className="font-mono text-xs hover:underline"
          >
            {formatMetaValue(value)}
          </Link>
        ) : (
          <span className="font-mono text-xs">{formatMetaValue(value)}</span>
        )}
      </div>
    </div>
  )
}

function scalarFilterHref(path: string, value: unknown): string | undefined {
  if (value === null || value === undefined) return undefined
  if (typeof value === "object") return undefined
  const text = formatMetaValue(value)
  if (!text || text === "—") return undefined
  return buildSingleFilterHref({
    meta: [{ key: path, op: "eq", value: text }],
  })
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success("Copied to clipboard")
  } catch {
    toast.error("Could not copy to clipboard")
  }
}
