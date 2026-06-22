import { Search } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useSearchPalette } from "@/hooks/use-search-palette"

/** Compact icon button that opens the global search palette. The visible
 * `⌘K` hint advertises the keyboard shortcut so users learn the faster path
 * after the first click. */
export function SearchTrigger() {
  const palette = useSearchPalette()

  return (
    <TooltipProvider delayDuration={150}>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="-mr-1 h-7 gap-1.5 px-1.5 text-muted-foreground hover:text-foreground"
            aria-label="Search files"
            onClick={() => palette.open()}
          >
            <Search className="size-3.5" />
            <kbd className="rounded border bg-muted px-1 font-mono text-[0.625rem] tracking-wide">
              ⌘K
            </kbd>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">Search files (⌘K)</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
