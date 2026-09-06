import type { ChartConfig } from "@/components/ui/chart"

export type ObservabilitySeriesTheme = {
  light: string
  dark: string
}

export type ObservabilitySeriesItem = {
  key: string
  label: string
  color?: string
  theme?: ObservabilitySeriesTheme
}

/** Primary rust — brand anchor */
const pithosysRust: ObservabilitySeriesTheme = {
  light: "#a83d2b",
  dark: "#c95a45",
}

/** Golden amber — lighter, reads clearly against rust and brown */
const pithosysAmber: ObservabilitySeriesTheme = {
  light: "#d8a657",
  dark: "#f0a261",
}

/** Deep umber — dark enough to separate from amber/orange stacks */
const pithosysUmber: ObservabilitySeriesTheme = {
  light: "#6b2418",
  dark: "#9a3a29",
}

/** Mid orange — between rust and amber */
const pithosysOrange: ObservabilitySeriesTheme = {
  light: "#c8793f",
  dark: "#d8a657",
}

export const bucketSyncSeries: ObservabilitySeriesItem[] = [
  { key: "sync_bucket", label: "Sync", theme: pithosysRust },
  { key: "scan_bucket", label: "Scan", theme: pithosysAmber },
]

export const objectSyncSeries: ObservabilitySeriesItem[] = [
  { key: "import_objects", label: "Import", theme: pithosysRust },
  { key: "refresh_objects", label: "Refresh", theme: pithosysAmber },
  { key: "remove_objects", label: "Remove", theme: pithosysUmber },
]

export const bucketEventSeries: ObservabilitySeriesItem[] = [
  { key: "created", label: "Created", theme: pithosysRust },
  { key: "removed", label: "Removed", theme: pithosysUmber },
  { key: "metadata_changed", label: "Metadata", theme: pithosysOrange },
  { key: "other", label: "Other", color: "var(--chart-5)" },
]

export function seriesToChartConfig(series: ObservabilitySeriesItem[]): ChartConfig {
  return Object.fromEntries(
    series.map((item) => [
      item.key,
      item.theme
        ? { label: item.label, theme: item.theme }
        : { label: item.label, color: item.color ?? "var(--chart-1)" },
    ])
  )
}
