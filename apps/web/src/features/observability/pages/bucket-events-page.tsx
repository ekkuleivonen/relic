import * as React from "react"

import { useBuckets } from "@/features/buckets/hooks/use-buckets"
import { BucketEventsTable } from "@/features/observability/components/bucket-events-table"
import {
  KindFilterButtons,
  type KindFilterOption,
} from "@/features/observability/components/kind-filter-buttons"
import { ObservabilityPageLayout } from "@/features/observability/components/observability-page-layout"
import { useBucketEventStats } from "@/features/observability/hooks/use-bucket-event-stats"
import { useBucketEvents } from "@/features/observability/hooks/use-bucket-events"
import { useObservabilityQueryState } from "@/features/observability/hooks/use-observability-query-state"
import { bucketEventSeries } from "@/features/observability/lib/observability-series"
import type { BucketEventCategory } from "@/types/bucket-events"

type BucketEventFilter = "all" | BucketEventCategory

const filterOptions: KindFilterOption<BucketEventFilter>[] = [
  { id: "all", label: "All" },
  { id: "created", label: "Created" },
  { id: "removed", label: "Removed" },
  { id: "metadata_changed", label: "Metadata" },
  { id: "other", label: "Other" },
]

export function BucketEventsPage() {
  const [filter, setFilter] = React.useState<BucketEventFilter>("all")
  const { range, page, timeRange, offset, pageSize, setRange, setPage, refreshTimeRange } =
    useObservabilityQueryState()

  const eventsQuery = useBucketEvents({
    category: filter === "all" ? undefined : filter,
    receivedAfter: timeRange.from,
    receivedBefore: timeRange.to,
    limit: pageSize,
    offset,
  })

  const pollInterval = hasPendingEvents(eventsQuery.data?.bucket_events)
    ? 3000
    : false

  const statsQuery = useBucketEventStats(
    {
      receivedAfter: timeRange.from,
      receivedBefore: timeRange.to,
    },
    { refetchInterval: pollInterval }
  )

  const bucketsQuery = useBuckets()
  const events = eventsQuery.data?.bucket_events ?? []
  const total = eventsQuery.data?.total ?? 0
  const bucketNames = Object.fromEntries(
    (bucketsQuery.data?.buckets ?? []).map((bucket) => [bucket.id, bucket.name])
  )
  const isRefreshing = eventsQuery.isFetching || statsQuery.isFetching

  function handleRefresh() {
    refreshTimeRange()
    void eventsQuery.refetch()
    void statsQuery.refetch()
  }

  function handleFilterChange(next: BucketEventFilter) {
    setFilter(next)
    setPage(1)
  }

  return (
    <ObservabilityPageLayout
      title="Bucket events"
      description="Storage notifications received through JetStream before they are batched into object sync jobs."
      range={range}
      onRangeChange={setRange}
      onRefresh={handleRefresh}
      isRefreshing={isRefreshing}
      series={bucketEventSeries}
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
      table={
        <BucketEventsTable events={events} bucketNames={bucketNames} />
      }
      isLoading={eventsQuery.isLoading}
      isError={eventsQuery.isError}
      onRetry={handleRefresh}
      isEmpty={eventsQuery.isSuccess && events.length === 0}
      emptyTitle="No bucket events in this range"
      emptyDescription="Events appear when upstream storage notifications are delivered to Pithosys through JetStream."
      total={total}
      page={page}
      pageSize={pageSize}
      onPageChange={setPage}
    />
  )
}

function hasPendingEvents(
  events: Array<{ state: string }> | undefined
) {
  return events?.some((event) => event.state === "pending") ?? false
}
