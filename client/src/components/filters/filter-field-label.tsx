import { CircleHelp } from "lucide-react"

import { Label } from "@/components/ui/label"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

type FilterFieldLabelProps = {
  htmlFor?: string
  label: string
  tooltip?: string
}

export function FilterFieldLabel({
  htmlFor,
  label,
  tooltip,
}: FilterFieldLabelProps) {
  return (
    <div className="flex items-center gap-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {tooltip && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              className="rounded-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
              aria-label={`About ${label}`}
            >
              <CircleHelp className="size-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs">
            {tooltip}
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}
