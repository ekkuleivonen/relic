import { Link } from "react-router"
import { AlertTriangleIcon } from "lucide-react"

import { JobRunStateBadge } from "@/features/job-runs/components/job-run-state-badge"
import { SyncProgressBar } from "@/features/job-runs/components/sync-progress-bar"
import {
  formatElapsedSince,
  formatStaleDuration,
  formatTraceProgress,
  formatStaleTraceMessage,
} from "@/features/job-runs/lib/format-sync-progress"
import type { JobRun, TraceSummary } from "@/types/job-runs"

type JobRunTraceProgressProps = {
  jobRun: JobRun
  traceSummary: TraceSummary
  detailHref?: string
  compact?: boolean
}

export function JobRunTraceProgress({
  jobRun,
  traceSummary,
  detailHref,
  compact = false,
}: JobRunTraceProgressProps) {
  const view = formatTraceProgress(traceSummary, jobRun.type)
  const elapsed = formatElapsedSince(jobRun.started_at)
  const href = detailHref ?? `/job-runs/${jobRun.id}`
  const staleMessage = formatStaleTraceMessage(traceSummary, jobRun.type)

  return (
    <div className="grid gap-3">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="font-medium">{view.phaseLabel}</div>
          <p className="mt-1 text-sm text-muted-foreground">{view.detailLine}</p>
        </div>
        <JobRunStateBadge state={traceSummary.state} />
      </div>

      {(view.isActive || view.isComplete) && (
        <SyncProgressBar value={view.progressPercent} />
      )}

      {!compact && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {elapsed && <span>Started {elapsed} ago</span>}
          {view.isActive && traceSummary.stale_seconds >= 0 && (
            <span>Last update {formatStaleDuration(traceSummary.stale_seconds)} ago</span>
          )}
          <Link
            to={href}
            className="font-medium text-foreground underline-offset-4 hover:underline"
          >
            View job run
          </Link>
        </div>
      )}

      {view.isStale && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-900 dark:text-amber-100">
          <AlertTriangleIcon className="mt-0.5 size-4 shrink-0" />
          <p>
            Progress has not updated in {formatStaleDuration(traceSummary.stale_seconds)}.
            {" "}
            {staleMessage}
          </p>
        </div>
      )}

      {view.isFailed && jobRun.error_message && (
        <p className="text-sm text-destructive">{jobRun.error_message}</p>
      )}
    </div>
  )
}
