import * as React from "react"

import { BucketSyncTable } from "@/features/observability/components/bucket-sync-table"
import {
  KindFilterButtons,
  type KindFilterOption,
} from "@/features/observability/components/kind-filter-buttons"
import { ObservabilityPageLayout } from "@/features/observability/components/observability-page-layout"
import { useBucketSyncRuns } from "@/features/observability/hooks/use-bucket-sync-runs"
import { useJobRunStats } from "@/features/observability/hooks/use-job-run-stats"
import { useObservabilityQueryState } from "@/features/observability/hooks/use-observability-query-state"
import { bucketSyncSeries } from "@/features/observability/lib/observability-series"
import type { JobRunType } from "@/types/job-runs"

type BucketSyncFilter = "all" | JobRunType

const filterOptions: KindFilterOption<BucketSyncFilter>[] = [
  { id: "all", label: "All" },
  { id: "sync_bucket", label: "Sync" },
  { id: "scan_bucket", label: "Scan" },
]

export function BucketSyncPage() {
  const [filter, setFilter] = React.useState<BucketSyncFilter>("all")
  const { range, page, timeRange, offset, pageSize, setRange, setPage, refreshTimeRange } =
    useObservabilityQueryState()

  const listQuery = useBucketSyncRuns({
    type: filter === "all" ? undefined : filter,
    createdAfter: timeRange.from,
    createdBefore: timeRange.to,
    limit: pageSize,
    offset,
  })

  const pollInterval = hasActiveJobRuns(listQuery.data?.job_runs) ? 3000 : false

  const statsQuery = useJobRunStats(
    {
      types: ["sync_bucket", "scan_bucket"],
      createdAfter: timeRange.from,
      createdBefore: timeRange.to,
    },
    { refetchInterval: pollInterval }
  )

  const jobRuns = listQuery.data?.job_runs ?? []
  const total = listQuery.data?.total ?? 0
  const isRefreshing = listQuery.isFetching || statsQuery.isFetching

  function handleRefresh() {
    refreshTimeRange()
    void listQuery.refetch()
    void statsQuery.refetch()
  }

  function handleFilterChange(next: BucketSyncFilter) {
    setFilter(next)
    setPage(1)
  }

  return (
    <ObservabilityPageLayout
      title="Bucket sync"
      description="Full reconciliations and verification scans that keep bucket catalogs aligned with upstream storage."
      range={range}
      onRangeChange={setRange}
      onRefresh={handleRefresh}
      isRefreshing={isRefreshing}
      series={bucketSyncSeries}
      stats={statsQuery.data}
      statsLoading={statsQuery.isPending}
      statsError={statsQuery.isError}
      tableFilters={
        <KindFilterButtons
          options={filterOptions}
          value={filter}
          onChange={handleFilterChange}
        />
      }
      table={<BucketSyncTable jobRuns={jobRuns} />}
      isLoading={listQuery.isLoading}
      isError={listQuery.isError}
      onRetry={handleRefresh}
      isEmpty={listQuery.isSuccess && jobRuns.length === 0}
      emptyTitle="No bucket sync runs in this range"
      emptyDescription="Queue a sync or scan from a bucket detail page to start reconciliation work."
      total={total}
      page={page}
      pageSize={pageSize}
      onPageChange={setPage}
    />
  )
}

function hasActiveJobRuns(
  jobRuns: Array<{ state: string }> | undefined
) {
  return (
    jobRuns?.some(
      (jobRun) => jobRun.state === "pending" || jobRun.state === "running"
    ) ?? false
  )
}
