import type { JobRun } from "@/types/job-runs"

export function formatJobRunType(type: string) {
  return type
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

export function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

export function formatOptionalDate(value: string | undefined) {
  return value ? formatDate(value) : "-"
}

export function formatProgressText(jobRun: JobRun) {
  const phase = stringifyPayloadValue(jobRun.progress.phase)
  const objectsSeen = stringifyPayloadValue(jobRun.progress.objects_seen)

  if (phase && objectsSeen) {
    return `${phase}, ${objectsSeen} objects seen`
  }

  if (phase) {
    return phase
  }

  if (objectsSeen) {
    return `${objectsSeen} objects seen`
  }

  if (jobRun.state === "pending") {
    return "Waiting to start"
  }

  if (jobRun.state === "running") {
    return "Running"
  }

  return "-"
}

function stringifyPayloadValue(value: unknown) {
  if (typeof value === "string" || typeof value === "number") {
    return String(value)
  }

  return ""
}
