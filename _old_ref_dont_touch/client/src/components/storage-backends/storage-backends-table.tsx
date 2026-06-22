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
import { storageBackendKindLabel } from "@/lib/storage-backends"
import { cn } from "@/lib/utils"
import type { StorageBackend } from "@/types/storage-backends"

type StorageBackendsTableProps = {
  storageBackends: StorageBackend[]
  isLoading: boolean
  probingId?: string
  drainingId?: string
  onEdit: (storageBackend: StorageBackend) => void
  onDelete: (storageBackend: StorageBackend) => void
  onProbe: (storageBackend: StorageBackend) => void
  onDrain: (storageBackend: StorageBackend) => void
}

export function StorageBackendsTable({
  storageBackends,
  isLoading,
  probingId,
  drainingId,
  onEdit,
  onDelete,
  onProbe,
  onDrain,
}: StorageBackendsTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
  }

  if (storageBackends.length === 0) {
    return (
      <div className="border px-4 py-10 text-center text-sm text-muted-foreground">
        No storage backends registered yet.
      </div>
    )
  }

  const sorted = rankByHotness(storageBackends)

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Hotness</TableHead>
          <TableHead>Kind</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Endpoint / Base path</TableHead>
          <TableHead>Region</TableHead>
          <TableHead>Namespace</TableHead>
          <TableHead>Objects</TableHead>
          <TableHead>Usage</TableHead>
          <TableHead>Avg latency</TableHead>
          <TableHead>Reachable</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((storageBackend, index) => (
          <TableRow key={storageBackend.id}>
            <TableCell>
              <HotnessBadge storageBackend={storageBackend} rank={index + 1} />
            </TableCell>
            <TableCell>
              <Badge variant="outline">
                {storageBackendKindLabel(storageBackend.kind)}
              </Badge>
            </TableCell>
            <TableCell className="font-medium">{storageBackend.name}</TableCell>
            <TableCell className="max-w-64 truncate">
              {storageBackend.endpoint}
            </TableCell>
            <TableCell>
              {storageBackend.kind === "filesystem" ? "—" : storageBackend.region}
            </TableCell>
            <TableCell className="font-mono text-xs">
              {storageBackend.namespace}
            </TableCell>
            <TableCell>{storageBackend.object_count}</TableCell>
            <TableCell>
              <StorageBackendUsage storageBackend={storageBackend} />
            </TableCell>
            <TableCell>
              <LatencyTag storageBackend={storageBackend} />
            </TableCell>
            <TableCell>
              <ReachableTag storageBackend={storageBackend} />
            </TableCell>
            <TableCell>
              <div className="flex justify-end gap-1">
                <ActionButton
                  label="Probe storage backend"
                  tooltip="Run sequential PUT, HEAD, GET, and DELETE probes; the result is appended to the backend's rolling probe history."
                  disabled={probingId === storageBackend.id}
                  onClick={() => onProbe(storageBackend)}
                >
                  <ActivityIcon />
                </ActionButton>
                <ActionButton
                  label="Drain storage backend"
                  tooltip="Migrate all blobs in this backend to colder backends with available capacity."
                  disabled={
                    drainingId === storageBackend.id ||
                    storageBackend.object_count === 0
                  }
                  onClick={() => onDrain(storageBackend)}
                >
                  <ArrowDownToLine />
                </ActionButton>
                <ActionButton
                  label="Edit storage backend"
                  tooltip="Edit mutable backend settings, limit, and credentials."
                  onClick={() => onEdit(storageBackend)}
                >
                  <PencilIcon />
                </ActionButton>
                <ActionButton
                  label="Delete storage backend"
                  tooltip="Delete this backend record if no blobs reference it."
                  variant="destructive"
                  onClick={() => onDelete(storageBackend)}
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

function rankByHotness(storageBackends: StorageBackend[]): StorageBackend[] {
  return [...storageBackends].sort((a, b) => {
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

function HotnessBadge({
  storageBackend,
  rank,
}: {
  storageBackend: StorageBackend
  rank: number
}) {
  if (!storageBackend.reachable) {
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

function StorageBackendUsage({
  storageBackend,
}: {
  storageBackend: StorageBackend
}) {
  const percentUsed =
    storageBackend.max_size_bytes === 0
      ? 0
      : Math.min(
          (storageBackend.current_size_bytes / storageBackend.max_size_bytes) *
            100,
          100
        )

  return (
    <div className="min-w-32 space-y-1.5">
      <Progress value={percentUsed} aria-label={`${percentUsed}% used`} />
      <div className="whitespace-nowrap text-xs text-muted-foreground">
        {formatBytes(storageBackend.current_size_bytes)} /{" "}
        {formatBytes(storageBackend.max_size_bytes)}
      </div>
    </div>
  )
}

function LatencyTag({ storageBackend }: { storageBackend: StorageBackend }) {
  const display =
    storageBackend.avg_latency_ms === null
      ? "--"
      : `${Math.round(storageBackend.avg_latency_ms)}ms`
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex min-w-12 items-center justify-center border bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {display}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        Rolling average across the last {storageBackend.probe_sample_count}{" "}
        successful probe
        {storageBackend.probe_sample_count === 1 ? "" : "s"}.
      </TooltipContent>
    </Tooltip>
  )
}

function ReachableTag({ storageBackend }: { storageBackend: StorageBackend }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "border",
        storageBackend.reachable
          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : "border-rose-500/30 bg-rose-500/10 text-rose-700 dark:text-rose-300"
      )}
    >
      {storageBackend.reachable ? "Yes" : "No"}
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

  return (
    new Intl.NumberFormat(undefined, {
      maximumFractionDigits: 1,
    }).format(value) + ` ${units[unitIndex]}`
  )
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
