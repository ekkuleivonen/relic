import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"

type SyncProgressBarProps = {
  value: number | null
  className?: string
}

export function SyncProgressBar({ value, className }: SyncProgressBarProps) {
  if (value === null) {
    return (
      <div
        className={cn(
          "relative h-1.5 w-full overflow-hidden rounded-full bg-muted",
          className
        )}
      >
        <div className="absolute inset-y-0 left-0 w-1/3 animate-pulse rounded-full bg-primary" />
      </div>
    )
  }

  return <Progress value={value} className={cn("h-1.5", className)} />
}
