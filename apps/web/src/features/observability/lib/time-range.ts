export type TimeRangePreset = "1h" | "24h" | "7d" | "30d"

export type TimeRangeBounds = {
  from: string
  to: string
}

export const TIME_RANGE_PRESETS: Array<{
  id: TimeRangePreset
  label: string
}> = [
  { id: "1h", label: "1 hour" },
  { id: "24h", label: "24 hours" },
  { id: "7d", label: "7 days" },
  { id: "30d", label: "30 days" },
]

const PRESET_DURATIONS: Record<TimeRangePreset, number> = {
  "1h": 60 * 60 * 1000,
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
}

export function isTimeRangePreset(value: string | null): value is TimeRangePreset {
  return value === "1h" || value === "24h" || value === "7d" || value === "30d"
}

export function presetToRange(preset: TimeRangePreset, anchor = new Date()): TimeRangeBounds {
  const to = anchor
  const from = new Date(to.getTime() - PRESET_DURATIONS[preset])

  return {
    from: from.toISOString(),
    to: to.toISOString(),
  }
}

export function timeRangePresetLabel(preset: TimeRangePreset) {
  return TIME_RANGE_PRESETS.find((entry) => entry.id === preset)?.label ?? preset
}
