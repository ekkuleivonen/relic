import { ActivityIcon, PencilIcon, Trash2Icon } from "lucide-react"
import type { ComponentProps, ReactNode } from "react"

import { BucketTierBadge } from "@/components/buckets/bucket-tier-badge"
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
import type { Bucket } from "@/types/buckets"

type BucketsTableProps = {
  buckets: Bucket[]
  isLoading: boolean
  probingId?: string
  onEdit: (bucket: Bucket) => void
  onDelete: (bucket: Bucket) => void
  onProbe: (bucket: Bucket) => void
}

export function BucketsTable({
  buckets,
  isLoading,
  probingId,
  onEdit,
  onDelete,
  onProbe,
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

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Tier</TableHead>
          <TableHead>Endpoint</TableHead>
          <TableHead>Region</TableHead>
          <TableHead>Bucket</TableHead>
          <TableHead>Objects</TableHead>
          <TableHead>Usage</TableHead>
          <TableHead>Put</TableHead>
          <TableHead>Head</TableHead>
          <TableHead>Get</TableHead>
          <TableHead>Delete</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {buckets.map((bucket) => (
          <TableRow key={bucket.id}>
            <TableCell className="font-medium">{bucket.name}</TableCell>
            <TableCell>
              <BucketTierBadge tier={bucket.tier} />
            </TableCell>
            <TableCell className="max-w-64 truncate">{bucket.endpoint}</TableCell>
            <TableCell>{bucket.region}</TableCell>
            <TableCell className="font-mono text-xs">{bucket.bucket}</TableCell>
            <TableCell>{bucket.object_count}</TableCell>
            <TableCell>
              <BucketUsage bucket={bucket} />
            </TableCell>
            <TableCell>
              <LatencyTag latencyMs={bucket.probe_latency_put_ms} />
            </TableCell>
            <TableCell>
              <LatencyTag latencyMs={bucket.probe_latency_head_ms} />
            </TableCell>
            <TableCell>
              <LatencyTag latencyMs={bucket.probe_latency_get_ms} />
            </TableCell>
            <TableCell>
              <LatencyTag latencyMs={bucket.probe_latency_delete_ms} />
            </TableCell>
            <TableCell>
              <div className="flex justify-end gap-1">
                <ActionButton
                  label="Probe bucket"
                  tooltip="Run sequential PUT, HEAD, GET, and DELETE probes with a test blob."
                  disabled={probingId === bucket.id}
                  onClick={() => onProbe(bucket)}
                >
                  <ActivityIcon />
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

function LatencyTag({ latencyMs }: { latencyMs: number | null }) {
  return (
    <span className="inline-flex min-w-12 items-center justify-center border bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
      {latencyMs === null ? "--" : `${latencyMs}ms`}
    </span>
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
