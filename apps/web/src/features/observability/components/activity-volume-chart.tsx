import { Bar, BarChart, CartesianGrid, XAxis } from "recharts"

import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { ObservabilitySeriesItem } from "@/features/observability/lib/observability-series"
import { seriesToChartConfig } from "@/features/observability/lib/observability-series"
import { timeRangePresetLabel, type TimeRangePreset } from "@/features/observability/lib/time-range"
import type { ActivityStats } from "@/types/observability-stats"

type ActivityVolumeChartProps = {
  series: ObservabilitySeriesItem[]
  stats: ActivityStats | undefined
  range: TimeRangePreset
  isLoading?: boolean
  isError?: boolean
}

export function ActivityVolumeChart({
  series,
  stats,
  range,
  isLoading,
  isError,
}: ActivityVolumeChartProps) {
  const chartConfig = seriesToChartConfig(series)
  const chartData = buildChartData(stats, series)
  const hasActivity = chartData.some((point) =>
    series.some((item) => Number(point[item.key] ?? 0) > 0)
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle>Activity</CardTitle>
        <CardDescription>
          Volume by kind over the last {timeRangePresetLabel(range).toLowerCase()}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && (
          <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
            Loading activity...
          </div>
        )}
        {isError && (
          <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
            Could not load activity chart.
          </div>
        )}
        {!isLoading && !isError && !hasActivity && (
          <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
            No activity in this time range.
          </div>
        )}
        {!isLoading && !isError && hasActivity && (
          <ChartContainer config={chartConfig} className="aspect-[3/1] w-full">
            <BarChart data={chartData}>
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={false}
                minTickGap={24}
              />
              <ChartTooltip content={<ChartTooltipContent />} />
              <ChartLegend content={<ChartLegendContent />} />
              {series.map((item) => (
                <Bar
                  key={item.key}
                  dataKey={item.key}
                  stackId="activity"
                  fill={`var(--color-${item.key})`}
                />
              ))}
            </BarChart>
          </ChartContainer>
        )}
      </CardContent>
    </Card>
  )
}

function buildChartData(
  stats: ActivityStats | undefined,
  series: ObservabilitySeriesItem[]
) {
  if (!stats) {
    return []
  }

  return stats.points.map((point) => {
    const row: Record<string, string | number> = {
      label: formatBucketLabel(point.start, stats.bucket),
    }

    for (const item of series) {
      row[item.key] = point.counts[item.key] ?? 0
    }

    return row
  })
}

function formatBucketLabel(value: string, bucket: ActivityStats["bucket"]) {
  const date = new Date(value)
  if (bucket === "day") {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
    }).format(date)
  }

  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(date)
}
