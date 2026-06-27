import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { DEFAULT_SCAN_INTERVAL } from "@/features/buckets/lib/scan-schedule"

type ScanScheduleFieldsProps = {
  enabled: boolean
  idPrefix: string
  interval: string
  onEnabledChange: (enabled: boolean) => void
  onIntervalChange: (interval: string) => void
}

export function ScanScheduleFields({
  enabled,
  idPrefix,
  interval,
  onEnabledChange,
  onIntervalChange,
}: ScanScheduleFieldsProps) {
  return (
    <div className="grid gap-4 rounded-lg border bg-background/60 p-3 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <div className="text-sm font-medium">Scheduled scan</div>
        <p className="mt-1 text-xs/6 text-muted-foreground">
          Relic can automatically queue verification scans on a fixed interval.
        </p>
      </div>

      <label className="flex items-start gap-3 sm:col-span-2">
        <Checkbox
          checked={enabled}
          onCheckedChange={(checked) => onEnabledChange(checked === true)}
        />
        <span>
          <span className="block text-sm font-medium">Enable scheduled scans</span>
          <span className="mt-1 block text-xs/6 text-muted-foreground">
            When enabled, the worker enqueues scan jobs if none are already
            running and this interval has elapsed since the last successful
            scan.
          </span>
        </span>
      </label>

      <div className="sm:col-span-2">
        <Label htmlFor={`${idPrefix}-scan-interval`}>Scan interval</Label>
        <div className="mt-1.5">
          <Input
            id={`${idPrefix}-scan-interval`}
            value={interval}
            onChange={(event) => onIntervalChange(event.target.value)}
            placeholder={DEFAULT_SCAN_INTERVAL}
            disabled={!enabled}
          />
        </div>
        <p className="mt-1.5 text-xs/6 text-muted-foreground">
          Minimum time between successful scans. Go duration format, for example{" "}
          <span className="font-mono">{DEFAULT_SCAN_INTERVAL}</span>,{" "}
          <span className="font-mono">6h</span>, or{" "}
          <span className="font-mono">30m</span>.
        </p>
      </div>
    </div>
  )
}
