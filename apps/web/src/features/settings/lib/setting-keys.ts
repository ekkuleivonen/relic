export type SettingFieldDefinition = {
  key: string
  label: string
  description: string
  type: "duration" | "boolean"
  defaultValue: string
}

export const workerSettingFields: SettingFieldDefinition[] = [
  {
    key: "WORKER_RUNNER_POLL_INTERVAL",
    label: "Job runner poll interval",
    description: "How long the job runner waits when no work is available.",
    type: "duration",
    defaultValue: "2s",
  },
  {
    key: "WORKER_RUNNER_RETRY_DELAY",
    label: "Job runner retry delay",
    description: "Backoff before retrying a failed job run.",
    type: "duration",
    defaultValue: "30s",
  },
  {
    key: "WORKER_SCAN_SCHEDULER_INTERVAL",
    label: "Scan scheduler interval",
    description: "How often the scan scheduler checks for due bucket scans.",
    type: "duration",
    defaultValue: "2s",
  },
  {
    key: "WORKER_SCAN_STAGGER",
    label: "Scan enqueue stagger",
    description: "Delay between enqueueing scan jobs for different buckets.",
    type: "duration",
    defaultValue: "30s",
  },
  {
    key: "WORKER_DUPLICATE_DETECTION_SCHEDULER_INTERVAL",
    label: "Duplicate detection scheduler interval",
    description: "How often the duplicate detection scheduler checks whether a run is due.",
    type: "duration",
    defaultValue: "2s",
  },
  {
    key: "WORKER_UPSTREAM_PROCESSOR_INTERVAL",
    label: "Upstream processor interval",
    description: "How often pending upstream events are processed.",
    type: "duration",
    defaultValue: "2s",
  },
  {
    key: "WORKER_CONFIG_REFETCH_INTERVAL",
    label: "Settings refetch interval",
    description: "How often the worker reloads runtime settings from the database.",
    type: "duration",
    defaultValue: "5m",
  },
]

export const jobsSettingFields: SettingFieldDefinition[] = [
  {
    key: "SCAN_BUCKET_ENABLED",
    label: "Enable scheduled bucket scans",
    description: "When enabled, the worker enqueues scan_bucket jobs on the global interval.",
    type: "boolean",
    defaultValue: "true",
  },
  {
    key: "SCAN_BUCKET_INTERVAL",
    label: "Scan interval",
    description: "Minimum time between successful scans for each bucket. Go duration format.",
    type: "duration",
    defaultValue: "24h",
  },
  {
    key: "DUPLICATE_DETECTION_ENABLED",
    label: "Enable duplicate detection",
    description: "When enabled, the worker schedules detect_duplicates jobs on the configured interval.",
    type: "boolean",
    defaultValue: "false",
  },
  {
    key: "DUPLICATE_DETECTION_INTERVAL",
    label: "Duplicate detection interval",
    description: "Minimum time between successful duplicate detection runs.",
    type: "duration",
    defaultValue: "24h",
  },
]

export function settingValueMap(items: Array<{ key: string; value: string }>) {
  return Object.fromEntries(items.map((item) => [item.key, item.value]))
}

export function parseBooleanSetting(value: string) {
  return value === "true"
}

export function formatBooleanSetting(enabled: boolean) {
  return enabled ? "true" : "false"
}
