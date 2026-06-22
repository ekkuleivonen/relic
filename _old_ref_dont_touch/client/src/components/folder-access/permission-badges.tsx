import { cn } from "@/lib/utils"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { PERMISSION_OPTIONS } from "@/types/folder-access"

type PermissionBadgesProps = {
  permissions: number
}

export function PermissionBadges({ permissions }: PermissionBadgesProps) {
  return (
    <div className="flex items-center gap-1">
      {PERMISSION_OPTIONS.map((option) => {
        const enabled = (permissions & option.bit) !== 0
        return (
          <Tooltip key={option.bit}>
            <TooltipTrigger asChild>
              <span
                className={cn(
                  "inline-flex size-6 items-center justify-center rounded-md border font-mono text-xs",
                  enabled
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-border text-muted-foreground/50"
                )}
                aria-label={`${option.label}${enabled ? "" : " (not granted)"}`}
              >
                {option.letter}
              </span>
            </TooltipTrigger>
            <TooltipContent>
              <div className="font-medium">{option.label}</div>
              <div className="text-xs text-muted-foreground">
                {option.description}
              </div>
            </TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}
