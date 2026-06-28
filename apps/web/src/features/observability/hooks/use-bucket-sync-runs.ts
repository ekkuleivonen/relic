import { useJobRuns } from "@/features/job-runs/hooks/use-job-runs"
import type { JobRunType, ListJobRunsParams } from "@/types/job-runs"

const bucketSyncTypes: JobRunType[] = ["sync_bucket", "scan_bucket"]

export function useBucketSyncRuns(
  params: Omit<ListJobRunsParams, "types"> = {},
  options: { refetchInterval?: number | false } = {}
) {
  const { type, ...rest } = params

  return useJobRuns(
    {
      ...rest,
      types: type ? [type] : bucketSyncTypes,
    },
    options
  )
}
