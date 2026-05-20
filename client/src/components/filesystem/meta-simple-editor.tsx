import { Plus, Trash2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { EditableMetaRow, MetaValueKind } from "@/lib/file-meta"
import { cn } from "@/lib/utils"

type MetaSimpleEditorProps = {
  rows: EditableMetaRow[]
  onChange: (rows: EditableMetaRow[]) => void
  onOpenJson: () => void
  className?: string
}

export function MetaSimpleEditor({
  rows,
  onChange,
  onOpenJson,
  className,
}: MetaSimpleEditorProps) {
  function updateRow(id: string, patch: Partial<EditableMetaRow>) {
    onChange(rows.map((row) => (row.id === id ? { ...row, ...patch } : row)))
  }

  function removeRow(id: string) {
    onChange(rows.filter((row) => row.id !== id))
  }

  function addRow() {
    const id = `new-${Date.now()}`
    onChange([
      ...rows,
      { id, path: "", valueText: "", kind: "string" },
    ])
  }

  return (
    <div className={cn("space-y-3", className)}>
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No fields yet. Add a key below or use the JSON editor for nested
          metadata.
        </p>
      ) : (
        <div className="overflow-hidden rounded-md border">
          <div className="grid grid-cols-[minmax(8rem,1fr)_minmax(10rem,1.5fr)_auto_auto] gap-2 border-b bg-muted/40 px-3 py-2 text-[0.625rem] font-semibold uppercase tracking-wide text-muted-foreground">
            <span>Key</span>
            <span>Value</span>
            <span className="w-24">Type</span>
            <span className="sr-only">Remove</span>
          </div>
          <div className="divide-y">
            {rows.map((row) => (
              <div
                key={row.id}
                className="grid grid-cols-[minmax(8rem,1fr)_minmax(10rem,1.5fr)_auto_auto] items-start gap-2 px-3 py-2"
              >
                <Input
                  value={row.path}
                  onChange={(event) =>
                    updateRow(row.id, { path: event.target.value })
                  }
                  placeholder="department"
                  className="h-8 font-mono text-xs"
                  spellCheck={false}
                />
                {row.kind === "complex" ? (
                  <p className="py-1.5 text-xs text-muted-foreground">
                    Nested value —{" "}
                    <button
                      type="button"
                      className="text-primary hover:underline"
                      onClick={onOpenJson}
                    >
                      edit as JSON
                    </button>
                  </p>
                ) : row.kind === "boolean" ? (
                  <Select
                    value={row.valueText || "true"}
                    onValueChange={(value) =>
                      updateRow(row.id, { valueText: value })
                    }
                  >
                    <SelectTrigger className="h-8 w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="true">true</SelectItem>
                      <SelectItem value="false">false</SelectItem>
                    </SelectContent>
                  </Select>
                ) : (
                  <Input
                    value={row.valueText}
                    onChange={(event) =>
                      updateRow(row.id, { valueText: event.target.value })
                    }
                    placeholder={
                      row.kind === "string_list"
                        ? "a, b, c"
                        : row.kind === "number"
                          ? "42"
                          : "value"
                    }
                    className="h-8 font-mono text-xs"
                    spellCheck={false}
                  />
                )}
                {row.kind === "complex" ? (
                  <span className="w-24 py-1.5 text-xs text-muted-foreground">
                    nested
                  </span>
                ) : (
                  <Select
                    value={row.kind}
                    onValueChange={(value) =>
                      updateRow(row.id, {
                        kind: value as MetaValueKind,
                        valueText:
                          value === "boolean"
                            ? "true"
                            : value === "string_list"
                              ? ""
                              : row.valueText,
                      })
                    }
                  >
                    <SelectTrigger className="h-8 w-24">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="string">text</SelectItem>
                      <SelectItem value="number">number</SelectItem>
                      <SelectItem value="boolean">bool</SelectItem>
                      <SelectItem value="string_list">list</SelectItem>
                    </SelectContent>
                  </Select>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="shrink-0 text-muted-foreground"
                  aria-label={`Remove ${row.path || "field"}`}
                  onClick={() => removeRow(row.id)}
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}

      <Button type="button" variant="outline" size="sm" onClick={addRow}>
        <Plus className="size-3.5" />
        Add field
      </Button>
    </div>
  )
}
