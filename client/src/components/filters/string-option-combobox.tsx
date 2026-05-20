import * as React from "react"
import { CheckIcon, ChevronsUpDownIcon } from "lucide-react"

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

type StringOptionComboboxProps = {
  options: readonly string[]
  value: string | undefined
  onChange: (value: string | undefined) => void
  disabled?: boolean
  placeholder?: string
  clearLabel?: string
  searchPlaceholder?: string
  mono?: boolean
}

export function StringOptionCombobox({
  options,
  value,
  onChange,
  disabled,
  placeholder = "Any",
  clearLabel,
  searchPlaceholder = "Search...",
  mono = false,
}: StringOptionComboboxProps) {
  const [open, setOpen] = React.useState(false)
  const resolvedClearLabel = clearLabel ?? placeholder

  const sorted = React.useMemo(
    () => options.slice().sort((a, b) => a.localeCompare(b)),
    [options]
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
          className="h-9 w-full justify-between font-normal"
        >
          <span
            className={cn(
              "truncate",
              mono ? "font-mono text-xs" : "text-sm",
              !value && "text-muted-foreground"
            )}
          >
            {value ?? placeholder}
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
          <CommandInput placeholder={searchPlaceholder} />
          <CommandList>
            <CommandEmpty>No matches found.</CommandEmpty>
            <CommandGroup>
              <CommandItem
                value={resolvedClearLabel}
                onSelect={() => {
                  onChange(undefined)
                  setOpen(false)
                }}
              >
                <span className="text-muted-foreground">{resolvedClearLabel}</span>
                <CheckIcon
                  className={cn("ml-auto", !value ? "opacity-100" : "opacity-0")}
                />
              </CommandItem>
              {sorted.map((option) => (
                <CommandItem
                  key={option}
                  value={option}
                  onSelect={() => {
                    onChange(option)
                    setOpen(false)
                  }}
                >
                  <span
                    className={cn("truncate", mono && "font-mono text-xs")}
                  >
                    {option}
                  </span>
                  <CheckIcon
                    className={cn(
                      "ml-auto",
                      option === value ? "opacity-100" : "opacity-0"
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
