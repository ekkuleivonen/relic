import type { JobRun, TraceSummary } from "@/types/job-runs"
import {
  formatSyncProgress,
  formatTraceProgress,
} from "@/features/job-runs/lib/format-sync-progress"

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
  const objectsListed = stringifyPayloadValue(jobRun.progress.objects_listed)
  const objectsSeen = stringifyPayloadValue(jobRun.progress.objects_seen)

  if (phase === "listing" && objectsListed) {
    return `Listing upstream, ${objectsListed} objects found`
  }

  if (phase && objectsListed) {
    return `${formatPhaseLabel(phase)}, ${objectsListed} objects listed`
  }

  if (phase && objectsSeen) {
    return `${formatPhaseLabel(phase)}, ${objectsSeen} objects seen`
  }

  if (phase) {
    return formatPhaseLabel(phase)
  }

  if (objectsListed) {
    return `${objectsListed} objects listed`
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

export function formatSyncProgressLine(traceSummary: TraceSummary) {
  return formatSyncProgress(traceSummary).detailLine
}

export function formatTraceProgressLine(
  traceSummary: TraceSummary,
  jobType: JobRun["type"]
) {
  return formatTraceProgress(traceSummary, jobType).detailLine
}

function formatPhaseLabel(phase: string) {
  switch (phase.toLowerCase()) {
    case "listing":
    case "listed":
      return "Listing upstream"
    case "planning":
      return "Comparing catalog"
    case "importing":
      return "Importing objects"
    case "refreshing":
      return "Refreshing objects"
    case "removing":
      return "Removing objects"
    case "applying":
      return "Applying changes"
    default:
      return phase
  }
}

function stringifyPayloadValue(value: unknown) {
  if (typeof value === "string" || typeof value === "number") {
    return String(value)
  }

  return ""
}
