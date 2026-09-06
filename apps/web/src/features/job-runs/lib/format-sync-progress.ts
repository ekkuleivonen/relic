import type { JobRunType, TraceSummary } from "@/types/job-runs"

export const SYNC_STALE_THRESHOLD_SECONDS = 120

export type SyncProgressView = {
  phaseLabel: string
  detailLine: string
  progressPercent: number | null
  isStale: boolean
  isActive: boolean
  isFailed: boolean
  isComplete: boolean
}

export function formatTraceProgress(
  summary: TraceSummary,
  jobType: JobRunType = "sync_bucket"
): SyncProgressView {
  if (jobType === "scan_bucket") {
    return formatScanProgress(summary)
  }

  return formatSyncProgress(summary)
}

export function formatStaleTraceMessage(
  summary: TraceSummary,
  jobType: JobRunType = "sync_bucket"
): string {
  const phase = normalizePhase(summary.phase)

  if (jobType === "scan_bucket") {
    switch (phase) {
      case "listing":
      case "listed":
      case "listing_upstream":
        return "Upstream listing may be slow or stalled."
      case "sampling_partitions":
      case "evaluating":
      case "escalating":
        return "Verification work may be slow or stalled."
      case "awaiting_sync":
        return "Scoped sync jobs may be slow or stalled."
      default:
        return "Scan progress may be stalled."
    }
  }

  switch (phase) {
    case "listing":
    case "listed":
    case "planning":
      return "Upstream listing may be slow or stalled."
    case "importing":
    case "refreshing":
    case "removing":
    case "applying":
      return "Catalog mutation batches may be slow or stalled."
    default:
      return "Sync progress may be stalled."
  }
}

export function formatSyncProgress(summary: TraceSummary): SyncProgressView {
  const phase = normalizePhase(summary.phase)
  const isActive =
    summary.state === "pending" || summary.state === "running"
  const isFailed = summary.state === "failed"
  const isComplete = summary.state === "succeeded"
  const isStale =
    isActive && summary.stale_seconds >= SYNC_STALE_THRESHOLD_SECONDS

  if (isFailed) {
    return {
      phaseLabel: "Sync failed",
      detailLine: failureDetail(summary),
      progressPercent: null,
      isStale: false,
      isActive: false,
      isFailed: true,
      isComplete: false,
    }
  }

  if (isComplete) {
    return {
      phaseLabel: "Sync complete",
      detailLine: completionDetail(summary),
      progressPercent: 100,
      isStale: false,
      isActive: false,
      isFailed: false,
      isComplete: true,
    }
  }

  if (summary.state === "pending") {
    return {
      phaseLabel: "Waiting to start",
      detailLine: "Sync is queued and will start shortly.",
      progressPercent: null,
      isStale,
      isActive,
      isFailed: false,
      isComplete: false,
    }
  }

  switch (phase) {
    case "listing":
    case "listed":
      return {
        phaseLabel: "Listing upstream objects",
        detailLine: listingDetail(summary),
        progressPercent: null,
        isStale,
        isActive,
        isFailed: false,
        isComplete: false,
      }
    case "planning":
      return {
        phaseLabel: "Comparing catalog",
        detailLine: "Diffing upstream listing against the local catalog.",
        progressPercent: null,
        isStale,
        isActive,
        isFailed: false,
        isComplete: false,
      }
    case "importing":
      return applyingView(summary, "Importing objects", "imported", isStale, isActive)
    case "refreshing":
      return applyingView(summary, "Refreshing objects", "refreshed", isStale, isActive)
    case "removing":
      return applyingView(summary, "Removing objects", "removed", isStale, isActive)
    case "applying":
      return applyingView(summary, "Applying catalog changes", "updated", isStale, isActive)
    default:
      return {
        phaseLabel: "Sync in progress",
        detailLine: summary.phase
          ? `Phase: ${summary.phase}`
          : "Worker is processing this sync.",
        progressPercent: overallProgressPercent(summary),
        isStale,
        isActive,
        isFailed: false,
        isComplete: false,
      }
  }
}

function formatScanProgress(summary: TraceSummary): SyncProgressView {
  const phase = normalizePhase(summary.phase)
  const isActive =
    summary.state === "pending" || summary.state === "running"
  const isFailed = summary.state === "failed"
  const isComplete = summary.state === "succeeded"
  const isStale =
    isActive && summary.stale_seconds >= SYNC_STALE_THRESHOLD_SECONDS

  if (isFailed) {
    return {
      phaseLabel: "Scan failed",
      detailLine: scanFailureDetail(summary),
      progressPercent: null,
      isStale: false,
      isActive: false,
      isFailed: true,
      isComplete: false,
    }
  }

  if (isComplete) {
    return {
      phaseLabel: "Scan complete",
      detailLine: scanCompletionDetail(summary),
      progressPercent: 100,
      isStale: false,
      isActive: false,
      isFailed: false,
      isComplete: true,
    }
  }

  if (summary.state === "pending") {
    return {
      phaseLabel: "Waiting to start",
      detailLine: "Scan is queued and will start shortly.",
      progressPercent: null,
      isStale,
      isActive,
      isFailed: false,
      isComplete: false,
    }
  }

  switch (phase) {
    case "sampling_partitions":
      return {
        phaseLabel: "Sampling partitions",
        detailLine: "Choosing verification partitions for this run.",
        progressPercent: null,
        isStale,
        isActive,
        isFailed: false,
        isComplete: false,
      }
    case "listing":
    case "listed":
    case "listing_upstream":
      return {
        phaseLabel: "Listing upstream objects",
        detailLine: listingDetail(summary),
        progressPercent: null,
        isStale,
        isActive,
        isFailed: false,
        isComplete: false,
      }
    case "evaluating":
      return {
        phaseLabel: "Evaluating fingerprints",
        detailLine: "Comparing local and upstream partition fingerprints.",
        progressPercent: null,
        isStale,
        isActive,
        isFailed: false,
        isComplete: false,
      }
    case "escalating":
      return {
        phaseLabel: "Escalating mismatches",
        detailLine: "Queueing scoped sync jobs for drifted partitions.",
        progressPercent: null,
        isStale,
        isActive,
        isFailed: false,
        isComplete: false,
      }
    case "awaiting_sync":
      return {
        phaseLabel: "Awaiting scoped sync",
        detailLine: scanAwaitingSyncDetail(summary),
        progressPercent: scanSyncProgressPercent(summary),
        isStale,
        isActive,
        isFailed: false,
        isComplete: false,
      }
    case "importing":
    case "refreshing":
    case "removing":
    case "applying":
      return applyingView(
        summary,
        "Reconciling catalog",
        "updated",
        isStale,
        isActive
      )
    default:
      return {
        phaseLabel: "Scan in progress",
        detailLine: summary.phase
          ? `Phase: ${summary.phase}`
          : "Worker is processing this scan.",
        progressPercent: scanSyncProgressPercent(summary),
        isStale,
        isActive,
        isFailed: false,
        isComplete: false,
      }
  }
}

function scanAwaitingSyncDetail(summary: TraceSummary) {
  const syncCounts = summary.job_counts.sync_bucket
  if (!syncCounts || syncCounts.total === 0) {
    return "Waiting for scoped sync jobs to finish."
  }

  return `${syncCounts.succeeded}/${syncCounts.total} scoped sync jobs complete`
}

function scanSyncProgressPercent(summary: TraceSummary): number | null {
  const syncCounts = summary.job_counts.sync_bucket
  if (!syncCounts || syncCounts.total <= 0) {
    return null
  }

  return Math.min(
    100,
    Math.round((syncCounts.succeeded / syncCounts.total) * 100)
  )
}

function scanCompletionDetail(summary: TraceSummary) {
  const syncCounts = summary.job_counts.sync_bucket
  if (syncCounts && syncCounts.total > 0) {
    return `${syncCounts.total} scoped sync ${syncCounts.total === 1 ? "job" : "jobs"} finished`
  }
  if (summary.objects_listed > 0) {
    return `${formatCount(summary.objects_listed)} objects checked, no drift found`
  }

  return "Bucket verification finished."
}

function scanFailureDetail(summary: TraceSummary) {
  const failedSyncs = summary.job_counts.sync_bucket?.failed ?? 0
  if (failedSyncs > 0) {
    return `${failedSyncs} scoped sync ${failedSyncs === 1 ? "job" : "jobs"} failed`
  }

  return "The scan trace finished with errors."
}

function applyingView(
  summary: TraceSummary,
  label: string,
  verb: "imported" | "refreshed" | "removed" | "updated",
  isStale: boolean,
  isActive: boolean
): SyncProgressView {
  const planned = totalPlanned(summary)
  const applied = totalApplied(summary)
  const batchLine = batchDetail(summary)

  let detailLine: string
  if (planned > 0) {
    detailLine = `${formatCount(applied)} / ${formatCount(planned)} objects ${verb}`
  } else if (summary.objects_listed > 0) {
    detailLine = `${formatCount(summary.objects_listed)} objects listed upstream`
  } else {
    detailLine = "Applying catalog mutations."
  }

  if (batchLine) {
    detailLine = `${detailLine} · ${batchLine}`
  }

  return {
    phaseLabel: label,
    detailLine,
    progressPercent: overallProgressPercent(summary),
    isStale,
    isActive,
    isFailed: false,
    isComplete: false,
  }
}

function listingDetail(summary: TraceSummary) {
  if (summary.objects_listed > 0) {
    return `${formatCount(summary.objects_listed)} objects found upstream`
  }

  return "Scanning object storage."
}

function completionDetail(summary: TraceSummary) {
  const applied = totalApplied(summary)
  if (applied > 0) {
    return `${formatCount(applied)} catalog objects updated`
  }
  if (summary.objects_listed > 0) {
    return `${formatCount(summary.objects_listed)} objects checked, catalog is up to date`
  }

  return "Bucket catalog matches upstream."
}

function failureDetail(summary: TraceSummary) {
  const failedBatches =
    summary.batches.import.failed +
    summary.batches.refresh.failed +
    summary.batches.remove.failed

  if (failedBatches > 0) {
    return `${failedBatches} batch ${failedBatches === 1 ? "job" : "jobs"} failed during sync`
  }

  return "The sync trace finished with errors."
}

function batchDetail(summary: TraceSummary) {
  const parts: string[] = []

  if (summary.batches.import.total > 0) {
    parts.push(
      `imports ${summary.batches.import.done}/${summary.batches.import.total}`
    )
  }
  if (summary.batches.refresh.total > 0) {
    parts.push(
      `refreshes ${summary.batches.refresh.done}/${summary.batches.refresh.total}`
    )
  }
  if (summary.batches.remove.total > 0) {
    parts.push(
      `removals ${summary.batches.remove.done}/${summary.batches.remove.total}`
    )
  }

  return parts.join(", ")
}

export function overallProgressPercent(summary: TraceSummary): number | null {
  const planned = totalPlanned(summary)
  if (planned <= 0) {
    return null
  }

  const applied = totalApplied(summary)
  return Math.min(100, Math.round((applied / planned) * 100))
}

function totalPlanned(summary: TraceSummary) {
  return (
    summary.objects_planned.import +
    summary.objects_planned.refresh +
    summary.objects_planned.remove
  )
}

function totalApplied(summary: TraceSummary) {
  return (
    summary.objects_applied.import +
    summary.objects_applied.refresh +
    summary.objects_applied.remove
  )
}

function normalizePhase(phase: string) {
  return phase.trim().toLowerCase()
}

export function formatCount(value: number) {
  return new Intl.NumberFormat().format(value)
}

export function formatStaleDuration(seconds: number) {
  if (seconds < 60) {
    return `${seconds}s`
  }

  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  if (minutes < 60) {
    return remainder > 0 ? `${minutes}m ${remainder}s` : `${minutes}m`
  }

  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`
}

export function formatElapsedSince(startedAt: string | undefined) {
  if (!startedAt) {
    return null
  }

  const started = new Date(startedAt)
  if (Number.isNaN(started.getTime())) {
    return null
  }

  const seconds = Math.max(0, Math.round((Date.now() - started.getTime()) / 1000))
  return formatStaleDuration(seconds)
}
