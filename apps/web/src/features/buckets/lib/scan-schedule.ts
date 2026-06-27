import type { BucketRelicConfig } from "@/types/buckets"

export const DEFAULT_SCAN_INTERVAL = "24h"

export type ScanScheduleFormState = {
  enabled: boolean
  interval: string
}

export function scanScheduleFromRelicConfig(
  relicConfig: BucketRelicConfig,
): ScanScheduleFormState {
  const scan = relicConfig.scan

  return {
    enabled: scan?.enabled !== false,
    interval: scan?.interval ?? DEFAULT_SCAN_INTERVAL,
  }
}

export function relicConfigFromScanSchedule(
  schedule: ScanScheduleFormState,
): BucketRelicConfig {
  return {
    scan: {
      enabled: schedule.enabled,
      interval: schedule.interval.trim() || DEFAULT_SCAN_INTERVAL,
    },
  }
}

export function formatScanScheduleSummary(
  relicConfig: BucketRelicConfig,
): { enabledLabel: string; intervalLabel: string } {
  const schedule = scanScheduleFromRelicConfig(relicConfig)

  return {
    enabledLabel: schedule.enabled ? "Enabled" : "Disabled",
    intervalLabel: schedule.enabled ? schedule.interval : "—",
  }
}
