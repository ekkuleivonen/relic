import { Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { UploadMetaRow } from "@/lib/upload-meta"
import { cn } from "@/lib/utils"

type UploadMetaFieldsProps = {
  rows: UploadMetaRow[]
  onChange: (rows: UploadMetaRow[]) => void
  className?: string
}

export function UploadMetaFields({
  rows,
  onChange,
  className,
}: UploadMetaFieldsProps) {
  function updateRow(id: string, patch: Partial<UploadMetaRow>) {
    onChange(rows.map((row) => (row.id === id ? { ...row, ...patch } : row)))
  }

  function removeRow(id: string) {
    onChange(rows.filter((row) => row.id !== id))
  }

  function addRow() {
    onChange([...rows, { id: `row-${Date.now()}`, key: "", value: "" }])
  }

  if (rows.length === 0) {
    return (
      <div className={cn("space-y-2", className)}>
        <Button type="button" variant="outline" size="sm" onClick={addRow}>
          <Plus className="size-3.5" />
          Add metadata field
        </Button>
      </div>
    )
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div className="overflow-hidden rounded-md border">
        <div className="grid grid-cols-[minmax(8rem,1fr)_minmax(10rem,1.5fr)_auto] gap-2 border-b bg-muted/40 px-3 py-2 text-[0.625rem] font-semibold uppercase tracking-wide text-muted-foreground">
          <span>Key</span>
          <span>Value</span>
          <span className="sr-only">Remove</span>
        </div>
        <div className="divide-y">
          {rows.map((row) => (
            <div
              key={row.id}
              className="grid grid-cols-[minmax(8rem,1fr)_minmax(10rem,1.5fr)_auto] items-center gap-2 px-3 py-2"
            >
              <Input
                value={row.key}
                onChange={(event) =>
                  updateRow(row.id, { key: event.target.value })
                }
                placeholder="department"
                className="h-8 font-mono text-xs"
                spellCheck={false}
              />
              <Input
                value={row.value}
                onChange={(event) =>
                  updateRow(row.id, { value: event.target.value })
                }
                placeholder="legal"
                className="h-8 font-mono text-xs"
                spellCheck={false}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="text-muted-foreground"
                aria-label={`Remove ${row.key || "field"}`}
                onClick={() => removeRow(row.id)}
              >
                <Trash2 className="size-3.5" />
              </Button>
            </div>
          ))}
        </div>
      </div>
      <Button type="button" variant="outline" size="sm" onClick={addRow}>
        <Plus className="size-3.5" />
        Add field
      </Button>
    </div>
  )
}
