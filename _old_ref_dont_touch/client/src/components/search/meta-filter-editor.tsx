import * as React from "react"
import { Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Popover,
  PopoverContent,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { META_OP_LABELS } from "@/lib/file-meta"
import {
  META_OPS,
  type FacetValue,
  type MetaFilter,
  type MetaOp,
} from "@/types/search"

type MetaFilterEditorProps = {
  onAdd: (filter: MetaFilter) => void
  /** Top-level meta keys in the matching result set, with file counts. */
  availableKeys: FacetValue[]
}

export function MetaFilterEditor({ onAdd, availableKeys }: MetaFilterEditorProps) {
  const [open, setOpen] = React.useState(false)
  const [key, setKey] = React.useState("")
  const [op, setOp] = React.useState<MetaOp>("gte")
  const [value, setValue] = React.useState("")
  const valueInputRef = React.useRef<HTMLInputElement>(null)

  function reset() {
    setKey("")
    setOp("gte")
    setValue("")
  }

  function commit() {
    const trimmedKey = key.trim()
    const trimmedValue = value.trim()
    if (!trimmedKey || !trimmedValue) return
    onAdd({ key: trimmedKey, op, value: trimmedValue })
    reset()
    setOpen(false)
  }

  function handleKeyPicked(picked: string) {
    setKey(picked)
    if (picked) {
      queueMicrotask(() => valueInputRef.current?.focus())
    }
  }

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (!next) reset()
        setOpen(next)
      }}
    >
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" size="sm" className="w-full">
          <Plus className="size-3" />
          Add metadata filter
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 gap-3">
        <PopoverHeader>
          <PopoverTitle>Add metadata filter</PopoverTitle>
          <p className="text-muted-foreground">
            Predicate over a metadata path, like{" "}
            <code>row_count ≥ 1000</code> or <code>department = legal</code>.
            Use dot paths for nested keys.
          </p>
        </PopoverHeader>

        <div className="space-y-1.5">
          <Label className="text-[0.625rem] uppercase tracking-wide text-muted-foreground">
            Key
          </Label>
          <MetaKeyPicker
            value={key}
            availableKeys={availableKeys}
            onPick={handleKeyPicked}
          />
        </div>

        <div className="space-y-2">
          <Label className="text-[0.625rem] uppercase tracking-wide text-muted-foreground">
            Operator
          </Label>
          <Select value={op} onValueChange={(next) => setOp(next as MetaOp)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {META_OPS.map((value) => (
                <SelectItem key={value} value={value}>
                  {META_OP_LABELS[value]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label
            htmlFor="meta-filter-value"
            className="text-[0.625rem] uppercase tracking-wide text-muted-foreground"
          >
            Value
          </Label>
          <Input
            id="meta-filter-value"
            ref={valueInputRef}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="1000"
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault()
                commit()
              }
            }}
          />
        </div>

        <div className="flex justify-end gap-1.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              reset()
              setOpen(false)
            }}
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={commit}
            disabled={!key.trim() || !value.trim()}
          >
            Add
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

type MetaKeyPickerProps = {
  value: string
  availableKeys: FacetValue[]
  onPick: (key: string) => void
}

function MetaKeyPicker({ value, availableKeys, onPick }: MetaKeyPickerProps) {
  const [search, setSearch] = React.useState("")

  const trimmed = search.trim()
  const knownKeys = React.useMemo(
    () => new Set(availableKeys.map((item) => item.value)),
    [availableKeys]
  )
  const showCustomOption = trimmed.length > 0 && !knownKeys.has(trimmed)

  return (
    <div className="overflow-hidden rounded-md border bg-popover">
      <Command>
        <CommandInput
          value={search}
          onValueChange={setSearch}
          placeholder={
            availableKeys.length > 0
              ? "Search metadata keys…"
              : "Type a metadata key…"
          }
          autoFocus
        />
        <CommandList className="max-h-44">
          {availableKeys.length === 0 && !trimmed ? (
            <CommandEmpty>
              No metadata keys in the current result set yet. Type one to use
              anyway.
            </CommandEmpty>
          ) : (
            <CommandEmpty>No matching key.</CommandEmpty>
          )}
          {showCustomOption && (
            <CommandGroup heading="Custom">
              <CommandItem
                value={`__custom__::${trimmed}`}
                onSelect={() => onPick(trimmed)}
              >
                <span className="truncate">
                  Use <code className="font-mono">{trimmed}</code>
                </span>
              </CommandItem>
            </CommandGroup>
          )}
          {availableKeys.length > 0 && (
            <CommandGroup heading="Available keys">
              {availableKeys.map((item) => (
                <CommandItem
                  key={item.value}
                  value={item.value}
                  data-checked={item.value === value}
                  onSelect={() => onPick(item.value)}
                >
                  <span className="truncate font-mono">{item.value}</span>
                  <span className="ml-auto text-[0.625rem] text-muted-foreground tabular-nums">
                    {item.count.toLocaleString()}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
        </CommandList>
      </Command>
      {value && (
        <div className="flex items-center justify-between border-t px-2.5 py-1.5 text-[0.625rem] text-muted-foreground">
          <span>
            Selected: <code className="font-mono text-foreground">{value}</code>
          </span>
          <button
            type="button"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => {
              onPick("")
              setSearch("")
            }}
          >
            Clear
          </button>
        </div>
      )}
    </div>
  )
}
