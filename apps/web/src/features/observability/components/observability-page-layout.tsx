import type { ReactNode } from "react"
import { Loader2Icon, RefreshCwIcon } from "lucide-react"

import { PageShell } from "@/components/page-shell"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ActivityVolumeChart } from "@/features/observability/components/activity-volume-chart"
import { ObservabilityPagination } from "@/features/observability/components/observability-pagination"
import { TimeRangeFilter } from "@/features/observability/components/time-range-filter"
import type { ObservabilitySeriesItem } from "@/features/observability/lib/observability-series"
import type { TimeRangePreset } from "@/features/observability/lib/time-range"
import type { ActivityStats } from "@/types/observability-stats"

type ObservabilityPageLayoutProps = {
  title: string
  description: string
  range: TimeRangePreset
  onRangeChange: (range: TimeRangePreset) => void
  onRefresh: () => void
  isRefreshing?: boolean
  series: ObservabilitySeriesItem[]
  stats: ActivityStats | undefined
  statsLoading?: boolean
  statsError?: boolean
  tableFilters?: ReactNode
  table: ReactNode
  isLoading?: boolean
  isError?: boolean
  onRetry?: () => void
  isEmpty?: boolean
  emptyTitle: string
  emptyDescription: string
  total: number
  page: number
  pageSize: number
  onPageChange: (page: number) => void
}

export function ObservabilityPageLayout({
  title,
  description,
  range,
  onRangeChange,
  onRefresh,
  isRefreshing,
  series,
  stats,
  statsLoading,
  statsError,
  tableFilters,
  table,
  isLoading,
  isError,
  onRetry,
  isEmpty,
  emptyTitle,
  emptyDescription,
  total,
  page,
  pageSize,
  onPageChange,
}: ObservabilityPageLayoutProps) {
  return (
    <PageShell>
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-4 max-w-2xl text-sm/7 text-muted-foreground">
            {description}
          </p>
        </div>
        <Button variant="outline" onClick={onRefresh} disabled={isRefreshing}>
          {isRefreshing ? (
            <Loader2Icon className="animate-spin" />
          ) : (
            <RefreshCwIcon />
          )}
          Refresh
        </Button>
      </header>

      <section className="mt-8 space-y-8">
        <TimeRangeFilter value={range} onChange={onRangeChange} />

        <ActivityVolumeChart
          series={series}
          stats={stats}
          range={range}
          isLoading={statsLoading}
          isError={statsError}
        />

        {tableFilters}

        {isLoading && <LoadingState />}
        {isError && onRetry && <ErrorState onRetry={onRetry} />}
        {!isLoading && !isError && isEmpty && (
          <EmptyState title={emptyTitle} description={emptyDescription} />
        )}
        {!isLoading && !isError && !isEmpty && (
          <>
            {table}
            <ObservabilityPagination
              total={total}
              page={page}
              pageSize={pageSize}
              onPageChange={onPageChange}
            />
          </>
        )}
      </section>
    </PageShell>
  )
}

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
        <Loader2Icon className="size-4 animate-spin" />
        Loading...
      </CardContent>
    </Card>
  )
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Could not load data</CardTitle>
        <CardDescription>
          Check that the API server is running, then retry the request.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button variant="outline" onClick={onRetry}>
          Retry
        </Button>
      </CardContent>
    </Card>
  )
}

function EmptyState({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
    </Card>
  )
}
