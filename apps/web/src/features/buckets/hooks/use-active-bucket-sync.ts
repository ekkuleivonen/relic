import { useJobRun, useJobRuns } from "@/features/job-runs/hooks/use-job-runs"
import { formatSyncProgress } from "@/features/job-runs/lib/format-sync-progress"
import type { TraceSummary } from "@/types/job-runs"

export function useActiveBucketSync(bucketId: string | undefined) {
  const latestSyncQuery = useJobRuns(
    {
      targetType: "bucket",
      targetId: bucketId,
      type: "sync_bucket",
      // Fetch enough rows to skip scan-escalated partition sync children client-side.
      limit: 50,
    },
    { enabled: Boolean(bucketId) }
  )

  const syncRuns = latestSyncQuery.data?.job_runs ?? []
  const latestSync = pickLatestRootSyncRun(syncRuns)
  const rootJobRunId = latestSync?.id

  const syncDetailQuery = useJobRun(rootJobRunId, { includeTraceSummary: true })

  const jobRun = syncDetailQuery.data
  const traceSummary = jobRun?.trace_summary
  const isActive = isActiveTrace(traceSummary)
  const progressView = traceSummary ? formatSyncProgress(traceSummary) : null

  return {
    jobRun,
    traceSummary,
    progressView,
    isActive,
    isLoading: latestSyncQuery.isLoading || syncDetailQuery.isLoading,
    isError: latestSyncQuery.isError || syncDetailQuery.isError,
    refetch: async () => {
      await Promise.all([latestSyncQuery.refetch(), syncDetailQuery.refetch()])
    },
    hasSyncHistory: Boolean(latestSync),
  }
}

function isActiveTrace(summary: TraceSummary | undefined) {
  return summary?.state === "pending" || summary?.state === "running"
}

function isRootSyncJob(run: { id: string; trace_id: string }) {
  return run.id === run.trace_id
}

function pickLatestRootSyncRun(
  syncRuns: Array<{ id: string; trace_id: string; state: string }>
) {
  const rootRuns = syncRuns.filter(isRootSyncJob)
  if (rootRuns.length === 0) {
    return undefined
  }

  const activeRun = rootRuns.find(
    (run) => run.state === "pending" || run.state === "running"
  )
  if (activeRun) {
    return activeRun
  }

  return rootRuns[0]
}
