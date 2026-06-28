import { Button } from "@/components/ui/button"
import {
  TIME_RANGE_PRESETS,
  type TimeRangePreset,
} from "@/features/observability/lib/time-range"

type TimeRangeFilterProps = {
  value: TimeRangePreset
  onChange: (value: TimeRangePreset) => void
}

export function TimeRangeFilter({ value, onChange }: TimeRangeFilterProps) {
  return (
    <div className="flex flex-wrap gap-2">
      {TIME_RANGE_PRESETS.map((preset) => (
        <Button
          key={preset.id}
          type="button"
          size="sm"
          variant={value === preset.id ? "default" : "outline"}
          onClick={() => onChange(preset.id)}
        >
          {preset.label}
        </Button>
      ))}
    </div>
  )
}
