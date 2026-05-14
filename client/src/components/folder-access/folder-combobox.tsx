import * as React from "react"
import { CheckIcon, ChevronsUpDownIcon, FolderIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"

type FolderSelectOption = {
  id: string
  path: string
}

type FolderComboboxProps = {
  folders: FolderSelectOption[]
  value: string | undefined
  onChange: (folderId: string) => void
  disabled?: boolean
  placeholder?: string
}

export function FolderCombobox({
  folders,
  value,
  onChange,
  disabled,
  placeholder = "Select a folder",
}: FolderComboboxProps) {
  const [open, setOpen] = React.useState(false)
  const selected = folders.find((folder) => folder.id === value)

  const sorted = React.useMemo(
    () => folders.slice().sort((a, b) => a.path.localeCompare(b.path)),
    [folders]
  )

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className="w-full justify-between font-normal"
        >
          <span
            className={cn(
              "truncate font-mono text-xs",
              !selected && "font-sans text-sm text-muted-foreground"
            )}
          >
            {selected ? selected.path : placeholder}
          </span>
          <ChevronsUpDownIcon className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-(--radix-popover-trigger-width) p-0" align="start">
        <Command
          filter={(itemValue, search) => {
            return itemValue.toLowerCase().includes(search.toLowerCase()) ? 1 : 0
          }}
        >
          <CommandInput placeholder="Search folder paths..." />
          <CommandList>
            <CommandEmpty>No folders found.</CommandEmpty>
            <CommandGroup>
              {sorted.map((entry) => (
                <CommandItem
                  key={entry.id}
                  value={entry.path}
                  onSelect={() => {
                    onChange(entry.id)
                    setOpen(false)
                  }}
                >
                  <FolderIcon className="size-3.5 shrink-0 opacity-60" />
                  <span className="truncate font-mono text-xs">
                    {entry.path}
                  </span>
                  <CheckIcon
                    className={cn(
                      "ml-auto",
                      entry.id === value ? "opacity-100" : "opacity-0"
                    )}
                  />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
