import * as React from "react"
import { Search, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

type SearchInputProps = {
  value: string
  onChange: (value: string) => void
  onSubmit?: (value: string) => void
  placeholder?: string
  autoFocus?: boolean
  debounceMs?: number
  className?: string
  inputClassName?: string
  ariaLabel?: string
}

/** Debounced text input with a clear button. The component owns the visible
 * draft so typing is responsive; `onChange` fires after `debounceMs` of
 * stillness, which is what calling code uses to update URL state. */
export function SearchInput({
  value,
  onChange,
  onSubmit,
  placeholder = "Search files…",
  autoFocus,
  debounceMs = 250,
  className,
  inputClassName,
  ariaLabel = "Search",
}: SearchInputProps) {
  const [draft, setDraft] = React.useState(value)
  const lastEmittedRef = React.useRef(value)

  React.useEffect(() => {
    if (value !== lastEmittedRef.current) {
      setDraft(value)
      lastEmittedRef.current = value
    }
  }, [value])

  React.useEffect(() => {
    if (draft === lastEmittedRef.current) return
    const handle = window.setTimeout(() => {
      lastEmittedRef.current = draft
      onChange(draft)
    }, debounceMs)
    return () => window.clearTimeout(handle)
  }, [debounceMs, draft, onChange])

  function emitNow(next: string) {
    setDraft(next)
    lastEmittedRef.current = next
    onChange(next)
  }

  return (
    <div className={cn("relative flex items-center", className)}>
      <Search className="pointer-events-none absolute left-2.5 size-3.5 text-muted-foreground" />
      <Input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault()
            emitNow(draft)
            onSubmit?.(draft)
          } else if (event.key === "Escape" && draft) {
            event.preventDefault()
            emitNow("")
          }
        }}
        placeholder={placeholder}
        aria-label={ariaLabel}
        autoFocus={autoFocus}
        className={cn("h-9 px-7 text-sm", inputClassName)}
      />
      {draft && (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="absolute right-1 size-6"
          aria-label="Clear search"
          onClick={() => emitNow("")}
        >
          <X className="size-3.5" />
        </Button>
      )}
    </div>
  )
}
