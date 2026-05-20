import * as React from "react"

import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { parseMetaPatchJson } from "@/lib/file-meta"
import { cn } from "@/lib/utils"

type MetaJsonEditorProps = {
  value: string
  onChange: (value: string) => void
  id?: string
  label?: string
  description?: string
  rows?: number
  className?: string
  error?: string | null
  onErrorChange?: (error: string | null) => void
}

export function MetaJsonEditor({
  value,
  onChange,
  id = "meta-json",
  label = "Metadata patch",
  description,
  rows = 10,
  className,
  error: controlledError,
  onErrorChange,
}: MetaJsonEditorProps) {
  const [localError, setLocalError] = React.useState<string | null>(null)
  const error = controlledError ?? localError

  function handleChange(next: string) {
    onChange(next)
    if (onErrorChange) {
      onErrorChange(null)
    } else {
      setLocalError(null)
    }
  }

  return (
    <div className={cn("grid gap-2", className)}>
      <Label htmlFor={id}>{label}</Label>
      {description ? (
        <p className="text-xs text-muted-foreground">{description}</p>
      ) : null}
      <Textarea
        id={id}
        value={value}
        onChange={(event) => handleChange(event.target.value)}
        rows={rows}
        className="font-mono text-xs"
        spellCheck={false}
      />
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  )
}

export function validateMetaJsonEditor(value: string): string | null {
  return parseMetaPatchJson(value).error
}
