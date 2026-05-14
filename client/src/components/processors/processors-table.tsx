import {
  ChevronRightIcon,
  PauseIcon,
  PlayIcon,
  RotateCcwIcon,
  SkipForwardIcon,
  Trash2Icon,
} from "lucide-react"
import * as React from "react"
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
import type { Processor, ProcessorFolderOption } from "@/types/processors"

type ProcessorsTableProps = {
  processors: Processor[]
  folders: ProcessorFolderOption[]
  isLoading: boolean
  onToggleEnabled: (processor: Processor) => void
  onRewind: (processor: Processor) => void
  onSkipStuck: (processor: Processor) => void
  onDelete: (processor: Processor) => void
  pendingProcessorId?: string
}

export function ProcessorsTable({
  processors,
  folders,
  isLoading,
  onToggleEnabled,
  onRewind,
  onSkipStuck,
  onDelete,
  pendingProcessorId,
}: ProcessorsTableProps) {
  const [expandedIds, setExpandedIds] = React.useState<Set<string>>(new Set())

  function toggleExpanded(processorId: string) {
    setExpandedIds((current) => {
      const next = new Set(current)
      if (next.has(processorId)) {
        next.delete(processorId)
      } else {
        next.add(processorId)
      }
      return next
    })
  }

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
          <TableHead>Folder scopes</TableHead>
          <TableHead className="text-right">Pending</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {processors.map((processor) => {
          const isPending = pendingProcessorId === processor.id
          const isSeed = processor.source === "seed"
          const isExpanded = expandedIds.has(processor.id)
          return (
            <React.Fragment key={processor.id}>
              <TableRow>
                <TableCell className="font-medium">
                  <button
                    type="button"
                    className="flex items-center gap-2 text-left hover:text-foreground"
                    onClick={() => toggleExpanded(processor.id)}
                    aria-expanded={isExpanded}
                  >
                    <ChevronRightIcon
                      className={`size-3.5 shrink-0 transition-transform ${
                        isExpanded ? "rotate-90" : ""
                      }`}
                    />
                    {processor.name}
                  </button>
                </TableCell>
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
                  <FolderScopeBadges processor={processor} folders={folders} />
                </TableCell>
                <TableCell className="text-right">
                  <PendingBadge count={processor.pending_count} />
                </TableCell>
              </TableRow>
              {isExpanded && (
                <TableRow>
                  <TableCell colSpan={6} className="bg-muted/20 p-4">
                    <div className="grid gap-4 md:grid-cols-[1fr_auto]">
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <DetailBlock label="Source">
                          <Badge variant={isSeed ? "secondary" : "outline"}>
                            {processor.source}
                          </Badge>
                        </DetailBlock>
                        <DetailBlock label="Cursor">
                          <span className="font-mono">
                            {processor.last_committed_offset.toLocaleString()} /{" "}
                            {processor.head_offset.toLocaleString()}
                          </span>
                        </DetailBlock>
                        <DetailBlock label="Last commit">
                          {processor.last_committed_at
                            ? formatDate(processor.last_committed_at)
                            : "—"}
                        </DetailBlock>
                        <DetailBlock label="Subscriptions">
                          <SubscriptionList
                            types={processor.subscribed_event_types}
                          />
                        </DetailBlock>
                      </div>
                      <div className="flex items-start justify-end gap-1">
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
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </React.Fragment>
          )
        })}
      </TableBody>
    </Table>
  )
}

function DetailBlock({
  label,
  children,
}: {
  label: string
  children: ReactNode
}) {
  return (
    <div className="space-y-1">
      <div className="text-[0.625rem] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="text-xs">{children}</div>
    </div>
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

function FolderScopeBadges({
  processor,
  folders,
}: {
  processor: Processor
  folders: ProcessorFolderOption[]
}) {
  if (processor.folder_scopes.length === 0) {
    return <span className="text-xs text-muted-foreground">all folders</span>
  }
  return (
    <div className="flex flex-wrap gap-1">
      {processor.folder_scopes.map((scope) => {
        const folder = folders.find((entry) => entry.id === scope.folder_id)
        const label = folder?.path ?? scope.folder_id
        return (
          <Badge
            key={`${scope.folder_id}:${scope.cascade}`}
            variant="outline"
            className="font-mono text-xs"
          >
            {label}
            {scope.cascade ? "/*" : ""}
          </Badge>
        )
      })}
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
