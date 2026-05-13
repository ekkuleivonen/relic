import {
  PauseIcon,
  PlayIcon,
  RotateCcwIcon,
  SkipForwardIcon,
  Trash2Icon,
} from "lucide-react"
import type { ComponentProps, ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import type { Processor } from "@/types/processors"

type ProcessorsTableProps = {
  processors: Processor[]
  isLoading: boolean
  onToggleEnabled: (processor: Processor) => void
  onRewind: (processor: Processor) => void
  onSkipStuck: (processor: Processor) => void
  onDelete: (processor: Processor) => void
  pendingProcessorId?: string
}

export function ProcessorsTable({
  processors,
  isLoading,
  onToggleEnabled,
  onRewind,
  onSkipStuck,
  onDelete,
  pendingProcessorId,
}: ProcessorsTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (processors.length === 0) {
    return (
      <div className="border px-4 py-10 text-center text-sm text-muted-foreground">
        No processors registered yet.
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Kind</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Failure</TableHead>
          <TableHead>Source</TableHead>
          <TableHead>Subscriptions</TableHead>
          <TableHead className="text-right">Cursor</TableHead>
          <TableHead className="text-right">Head</TableHead>
          <TableHead className="text-right">Pending</TableHead>
          <TableHead>Last commit</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {processors.map((processor) => {
          const isPending = pendingProcessorId === processor.id
          const isSeed = processor.source === "seed"
          return (
            <TableRow key={processor.id}>
              <TableCell className="font-medium">{processor.name}</TableCell>
              <TableCell>
                <Badge variant="outline" className="font-mono text-xs">
                  {processor.kind}
                </Badge>
              </TableCell>
              <TableCell>
                <StatusBadge enabled={processor.enabled} />
              </TableCell>
              <TableCell>
                <FailureBadge processor={processor} />
              </TableCell>
              <TableCell>
                <Badge variant={isSeed ? "secondary" : "outline"}>
                  {processor.source}
                </Badge>
              </TableCell>
              <TableCell>
                <SubscriptionList types={processor.subscribed_event_types} />
              </TableCell>
              <TableCell className="text-right font-mono text-xs">
                {processor.last_committed_offset.toLocaleString()}
              </TableCell>
              <TableCell className="text-right font-mono text-xs">
                {processor.head_offset.toLocaleString()}
              </TableCell>
              <TableCell className="text-right">
                <PendingBadge count={processor.pending_count} />
              </TableCell>
              <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                {processor.last_committed_at
                  ? formatDate(processor.last_committed_at)
                  : "—"}
              </TableCell>
              <TableCell>
                <div className="flex justify-end gap-1">
                  <ActionButton
                    label={processor.enabled ? "Pause" : "Resume"}
                    tooltip={
                      processor.enabled
                        ? "Pause this processor. The dispatcher stops enqueueing until resumed."
                        : "Resume this processor. The dispatcher will pick up from the cursor."
                    }
                    onClick={() => onToggleEnabled(processor)}
                    disabled={isPending}
                  >
                    {processor.enabled ? <PauseIcon /> : <PlayIcon />}
                  </ActionButton>
                  <ActionButton
                    label="Rewind cursor"
                    tooltip="Move the cursor backward to replay events. Handlers must be idempotent."
                    onClick={() => onRewind(processor)}
                    disabled={isPending}
                  >
                    <RotateCcwIcon />
                  </ActionButton>
                  <ActionButton
                    label="Skip stuck event"
                    tooltip="Advance the cursor past a poisoned event. The action is audited."
                    onClick={() => onSkipStuck(processor)}
                    disabled={isPending || processor.pending_count === 0}
                  >
                    <SkipForwardIcon />
                  </ActionButton>
                  <ActionButton
                    label="Delete processor"
                    tooltip={
                      isSeed
                        ? "Seeded processors cannot be deleted."
                        : "Delete this admin-managed processor."
                    }
                    variant="destructive"
                    onClick={() => onDelete(processor)}
                    disabled={isPending || isSeed}
                  >
                    <Trash2Icon />
                  </ActionButton>
                </div>
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

function StatusBadge({ enabled }: { enabled: boolean }) {
  return (
    <Badge variant={enabled ? "secondary" : "destructive"}>
      {enabled ? "enabled" : "paused"}
    </Badge>
  )
}

function PendingBadge({ count }: { count: number }) {
  if (count === 0) {
    return <span className="text-xs text-muted-foreground">0</span>
  }
  return (
    <Badge variant="default" className="font-mono text-xs">
      {count.toLocaleString()}
    </Badge>
  )
}

function FailureBadge({ processor }: { processor: Processor }) {
  if (!processor.last_failed_event_id) {
    return <span className="text-xs text-muted-foreground">—</span>
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Badge variant="destructive" className="max-w-48 truncate text-xs">
          {processor.last_error_class ?? "failed"}
        </Badge>
      </TooltipTrigger>
      <TooltipContent className="max-w-96">
        <div className="space-y-1">
          <div className="font-mono text-xs">{processor.last_failed_event_id}</div>
          {processor.last_error_message && (
            <div className="text-xs">{processor.last_error_message}</div>
          )}
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

function SubscriptionList({ types }: { types: string[] }) {
  if (types.length === 0) {
    return <span className="text-xs text-muted-foreground">—</span>
  }
  return (
    <div className="flex flex-wrap gap-1">
      {types.map((type) => (
        <Badge key={type} variant="outline" className="font-mono text-xs">
          {type}
        </Badge>
      ))}
    </div>
  )
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value))
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
