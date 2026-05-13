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
import {
  KVS_OPS,
  type FacetValue,
  type KvsFilter,
  type KvsOp,
} from "@/types/search"

type KvsFilterEditorProps = {
  onAdd: (filter: KvsFilter) => void
  /** kvs keys that exist in the matching result set, with file counts.
   * Used to populate the key picker so the user picks from real data
   * instead of guessing. The user can still enter a custom key. */
  availableKeys: FacetValue[]
}

const OP_LABELS: Record<KvsOp, string> = {
  eq: "= equals",
  neq: "≠ not equals",
  gt: "> greater than",
  gte: "≥ at least",
  lt: "< less than",
  lte: "≤ at most",
}

/** Inline popover for adding a kvs predicate (e.g. row_count >= 1000). The
 * panel keeps the affordance for power-user range queries discoverable
 * without giving every kvs key its own dedicated UI. */
export function KvsFilterEditor({ onAdd, availableKeys }: KvsFilterEditorProps) {
  const [open, setOpen] = React.useState(false)
  const [key, setKey] = React.useState("")
  const [op, setOp] = React.useState<KvsOp>("gte")
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
          Add kvs filter
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 gap-3">
        <PopoverHeader>
          <PopoverTitle>Add kvs filter</PopoverTitle>
          <p className="text-muted-foreground">
            Predicate over a single <code>meta.kvs</code> key, like{" "}
            <code>row_count ≥ 1000</code>.
          </p>
        </PopoverHeader>

        <div className="space-y-1.5">
          <Label className="text-[0.625rem] uppercase tracking-wide text-muted-foreground">
            Key
          </Label>
          <KvsKeyPicker
            value={key}
            availableKeys={availableKeys}
            onPick={handleKeyPicked}
          />
        </div>

        <div className="space-y-2">
          <Label className="text-[0.625rem] uppercase tracking-wide text-muted-foreground">
            Operator
          </Label>
          <Select value={op} onValueChange={(next) => setOp(next as KvsOp)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KVS_OPS.map((value) => (
                <SelectItem key={value} value={value}>
                  {OP_LABELS[value]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label
            htmlFor="kvs-value"
            className="text-[0.625rem] uppercase tracking-wide text-muted-foreground"
          >
            Value
          </Label>
          <Input
            id="kvs-value"
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

type KvsKeyPickerProps = {
  value: string
  availableKeys: FacetValue[]
  onPick: (key: string) => void
}

/** Searchable picker for `meta.kvs` keys present in the dataset. Falls
 * back to a "use as custom key" option when the typed text doesn't match
 * any known key, so we never block niche keys produced by new toolchains. */
function KvsKeyPicker({ value, availableKeys, onPick }: KvsKeyPickerProps) {
  // The popover unmounts on close, so component state naturally resets per
  // open. We don't sync `value` -> `search`: the search input is just a
  // filter; the selected key lives in the parent and is rendered separately.
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
              ? "Search kvs keys…"
              : "Type a kvs key…"
          }
          autoFocus
        />
        <CommandList className="max-h-44">
          {availableKeys.length === 0 && !trimmed ? (
            <CommandEmpty>
              No kvs keys in the current result set yet. Type one to use
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
