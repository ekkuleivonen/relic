import * as React from "react"
import { useSearchParams } from "react-router"

import { KindFilterButtons } from "@/features/observability/components/kind-filter-buttons"
import { ObjectSyncTable } from "@/features/observability/components/object-sync-table"
import { ObservabilityPageLayout } from "@/features/observability/components/observability-page-layout"
import { useJobRunStats } from "@/features/observability/hooks/use-job-run-stats"
import { useObjectSyncRuns } from "@/features/observability/hooks/use-object-sync-runs"
import { useObservabilityQueryState } from "@/features/observability/hooks/use-observability-query-state"
import { objectSyncSeries } from "@/features/observability/lib/observability-series"
import type { JobRunType } from "@/types/job-runs"

type ObjectSyncFilter = "all" | JobRunType

const filterOptions = [
  { id: "all" as const, label: "All" },
  { id: "import_objects" as const, label: "Imports" },
  { id: "refresh_objects" as const, label: "Refreshes" },
  { id: "remove_objects" as const, label: "Removals" },
]

export function ObjectSyncPage() {
  const [searchParams] = useSearchParams()
  const bucketId = searchParams.get("bucket") ?? undefined
  const [filter, setFilter] = React.useState<ObjectSyncFilter>("all")
  const { range, page, timeRange, offset, pageSize, setRange, setPage, refreshTimeRange } =
    useObservabilityQueryState()

  const listQuery = useObjectSyncRuns({
    type: filter === "all" ? undefined : filter,
    targetId: bucketId,
    requestedByType: bucketId ? "upstream_event" : undefined,
    createdAfter: timeRange.from,
    createdBefore: timeRange.to,
    limit: pageSize,
    offset,
  })

  const pollInterval = hasActiveJobRuns(listQuery.data?.job_runs) ? 3000 : false

  const statsQuery = useJobRunStats(
    {
      types: ["import_objects", "remove_objects", "refresh_objects"],
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

  function handleFilterChange(next: ObjectSyncFilter) {
    setFilter(next)
    setPage(1)
  }

  return (
    <ObservabilityPageLayout
      title="Object sync"
      description={`Catalog mutations that import, refresh, or remove objects after sync planning or bucket storage notifications.${bucketId ? " Filtered to bucket-event runs for one bucket." : ""}`}
      range={range}
      onRangeChange={setRange}
      onRefresh={handleRefresh}
      isRefreshing={isRefreshing}
      series={objectSyncSeries}
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
      table={<ObjectSyncTable jobRuns={jobRuns} />}
      isLoading={listQuery.isLoading}
      isError={listQuery.isError}
      onRetry={handleRefresh}
      isEmpty={listQuery.isSuccess && jobRuns.length === 0}
      emptyTitle="No object sync runs in this range"
      emptyDescription="Object sync jobs appear after bucket reconciliation or when bucket storage events are processed."
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
