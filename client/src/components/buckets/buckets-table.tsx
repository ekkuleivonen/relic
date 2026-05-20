import { ActivityIcon, ArrowDownToLine, PencilIcon, Trash2Icon } from "lucide-react"
import type { ComponentProps, ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"
import type { Bucket } from "@/types/buckets"

type BucketsTableProps = {
  buckets: Bucket[]
  isLoading: boolean
  probingId?: string
  drainingId?: string
  onEdit: (bucket: Bucket) => void
  onDelete: (bucket: Bucket) => void
  onProbe: (bucket: Bucket) => void
  onDrain: (bucket: Bucket) => void
}

export function BucketsTable({
  buckets,
  isLoading,
  probingId,
  drainingId,
  onEdit,
  onDelete,
  onProbe,
  onDrain,
}: BucketsTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
  }

  if (buckets.length === 0) {
    return (
      <div className="border px-4 py-10 text-center text-sm text-muted-foreground">
        No bucket backends registered yet.
      </div>
    )
  }

  const sorted = rankByHotness(buckets)

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Hotness</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Endpoint</TableHead>
          <TableHead>Region</TableHead>
          <TableHead>Bucket</TableHead>
          <TableHead>Objects</TableHead>
          <TableHead>Usage</TableHead>
          <TableHead>Avg latency</TableHead>
          <TableHead>Reachable</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((bucket, index) => (
          <TableRow key={bucket.id}>
            <TableCell>
              <HotnessBadge bucket={bucket} rank={index + 1} />
            </TableCell>
            <TableCell className="font-medium">{bucket.name}</TableCell>
            <TableCell className="max-w-64 truncate">{bucket.endpoint}</TableCell>
            <TableCell>{bucket.region}</TableCell>
            <TableCell className="font-mono text-xs">{bucket.bucket}</TableCell>
            <TableCell>{bucket.object_count}</TableCell>
            <TableCell>
              <BucketUsage bucket={bucket} />
            </TableCell>
            <TableCell>
              <LatencyTag bucket={bucket} />
            </TableCell>
            <TableCell>
              <ReachableTag bucket={bucket} />
            </TableCell>
            <TableCell>
              <div className="flex justify-end gap-1">
                <ActionButton
                  label="Probe bucket"
                  tooltip="Run sequential PUT, HEAD, GET, and DELETE probes; the result is appended to the bucket's rolling probe history."
                  disabled={probingId === bucket.id}
                  onClick={() => onProbe(bucket)}
                >
                  <ActivityIcon />
                </ActionButton>
                <ActionButton
                  label="Drain bucket"
                  tooltip="Migrate all blobs in this bucket to colder backends with available capacity."
                  disabled={drainingId === bucket.id || bucket.object_count === 0}
                  onClick={() => onDrain(bucket)}
                >
                  <ArrowDownToLine />
                </ActionButton>
                <ActionButton
                  label="Edit bucket"
                  tooltip="Edit mutable bucket settings, limit, and credentials."
                  onClick={() => onEdit(bucket)}
                >
                  <PencilIcon />
                </ActionButton>
                <ActionButton
                  label="Delete bucket"
                  tooltip="Delete this bucket record if no blobs reference it."
                  variant="destructive"
                  onClick={() => onDelete(bucket)}
                >
                  <Trash2Icon />
                </ActionButton>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function rankByHotness(buckets: Bucket[]): Bucket[] {
  return [...buckets].sort((a, b) => {
    if (a.reachable !== b.reachable) return a.reachable ? -1 : 1
    if (a.avg_latency_ms === null && b.avg_latency_ms === null) {
      return a.name.localeCompare(b.name)
    }
    if (a.avg_latency_ms === null) return 1
    if (b.avg_latency_ms === null) return -1
    if (a.avg_latency_ms !== b.avg_latency_ms) {
      return a.avg_latency_ms - b.avg_latency_ms
    }
    return a.name.localeCompare(b.name)
  })
}

function HotnessBadge({ bucket, rank }: { bucket: Bucket; rank: number }) {
  if (!bucket.reachable) {
    return (
      <Badge
        variant="outline"
        className="border border-zinc-500/30 bg-zinc-500/10 text-zinc-700 dark:text-zinc-300"
      >
        Unreachable
      </Badge>
    )
  }
  const styles = [
    "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300",
    "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
    "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300",
  ]
  const style = styles[Math.min(rank - 1, styles.length - 1)]
  return (
    <Badge variant="outline" className={cn("border", style)}>
      #{rank} hottest
    </Badge>
  )
}

function BucketUsage({ bucket }: { bucket: Bucket }) {
  const percentUsed =
    bucket.max_size_bytes === 0
      ? 0
      : Math.min((bucket.current_size_bytes / bucket.max_size_bytes) * 100, 100)

  return (
    <div className="min-w-32 space-y-1.5">
      <Progress value={percentUsed} aria-label={`${percentUsed}% used`} />
      <div className="whitespace-nowrap text-xs text-muted-foreground">
        {formatBytes(bucket.current_size_bytes)} / {formatBytes(bucket.max_size_bytes)}
      </div>
    </div>
  )
}

function LatencyTag({ bucket }: { bucket: Bucket }) {
  const display =
    bucket.avg_latency_ms === null
      ? "--"
      : `${Math.round(bucket.avg_latency_ms)}ms`
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex min-w-12 items-center justify-center border bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {display}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        Rolling average across the last {bucket.probe_sample_count} successful
        probe{bucket.probe_sample_count === 1 ? "" : "s"}.
      </TooltipContent>
    </Tooltip>
  )
}

function ReachableTag({ bucket }: { bucket: Bucket }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "border",
        bucket.reachable
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300"
      )}
    >
      {bucket.reachable ? "Yes" : "No"}
    </Badge>
  )
}

function formatBytes(bytes: number) {
  const units = ["B", "KB", "MB", "GB", "TB", "PB"] as const
  let value = bytes
  let unitIndex = 0

  while (value >= 1000 && unitIndex < units.length - 1) {
    value /= 1000
    unitIndex += 1
  }

  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 1,
  }).format(value) + ` ${units[unitIndex]}`
}

type ActionButtonProps = {
  label: string
  tooltip: string
  children: ReactNode
  variant?: ComponentProps<typeof Button>["variant"]
  disabled?: boolean
  onClick: () => void
}

function ActionButton({
  label,
  tooltip,
  children,
  variant = "outline",
  disabled = false,
  onClick,
}: ActionButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant={variant}
          size="icon-sm"
          onClick={onClick}
          disabled={disabled}
        >
          {children}
          <span className="sr-only">{label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  )
}
