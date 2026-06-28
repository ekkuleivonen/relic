import { useJobRuns } from "@/features/job-runs/hooks/use-job-runs"
import type { JobRunType } from "@/types/job-runs"

const objectSyncTypes: JobRunType[] = [
  "import_objects",
  "remove_objects",
  "refresh_objects",
]

export function useObjectSyncRuns(
  options: {
    type?: JobRunType
    requestedByType?: string
    targetId?: string
    createdAfter?: string
    createdBefore?: string
    limit?: number
    offset?: number
  } = {},
  queryOptions: { refetchInterval?: number | false } = {}
) {
  const {
    type,
    requestedByType,
    targetId,
    createdAfter,
    createdBefore,
    limit,
    offset,
  } = options

  return useJobRuns(
    {
      types: type ? [type] : objectSyncTypes,
      requestedByType,
      targetId,
      targetType: targetId ? "bucket" : undefined,
      createdAfter,
      createdBefore,
      limit,
      offset,
    },
    queryOptions
  )
}
