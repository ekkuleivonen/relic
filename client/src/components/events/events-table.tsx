import * as React from "react"
import { ChevronRight } from "lucide-react"

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
import { cn } from "@/lib/utils"
import type { EventRecord } from "@/types/events"

type EventsTableProps = {
  events: EventRecord[]
  isLoading: boolean
}

export function EventsTable({ events, isLoading }: EventsTableProps) {
  const [expandedEventIds, setExpandedEventIds] = React.useState<Set<string>>(
    () => new Set()
  )

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (events.length === 0) {
    return (
      <div className="border px-4 py-10 text-center text-sm text-muted-foreground">
        No events match these filters.
      </div>
    )
  }

  function toggleExpanded(eventId: string) {
    setExpandedEventIds((current) => {
      const next = new Set(current)

      if (next.has(eventId)) {
        next.delete(eventId)
      } else {
        next.add(eventId)
      }

      return next
    })
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>Event</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Actor</TableHead>
          <TableHead>Request</TableHead>
          <TableHead>Related</TableHead>
          <TableHead className="text-right">Details</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map((event) => {
          const isExpanded = expandedEventIds.has(event.id)
          const hasMetadata = Object.keys(event.metadata).length > 0
          const hasRelatedIds =
            event.file_ids.length > 0 ||
            event.folder_ids.length > 0 ||
            event.blob_ids.length > 0
          const hasDetails = hasMetadata || hasRelatedIds

          return (
            <React.Fragment key={event.id}>
              <TableRow>
                <TableCell className="whitespace-nowrap text-xs">
                  {formatDate(event.created_at)}
                </TableCell>
                <TableCell>
                  <div className="space-y-1">
                    <div className="font-medium">{event.operation}</div>
                    <div className="font-mono text-xs text-muted-foreground">
                      {event.source}
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <StatusBadge status={event.status} />
                </TableCell>
                <TableCell>
                  {event.actor ? (
                    <div className="space-y-1">
                      <div className="text-sm">{event.actor.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {event.actor.email}
                      </div>
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      System
                    </span>
                  )}
                </TableCell>
                <TableCell className="max-w-48 truncate font-mono text-xs">
                  {event.request_id ?? "—"}
                </TableCell>
                <TableCell>
                  <RelatedCounts event={event} />
                </TableCell>
                <TableCell className="text-right">
                  {hasDetails ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-expanded={isExpanded}
                      onClick={() => toggleExpanded(event.id)}
                    >
                      <ChevronRight
                        className={cn(
                          "size-3 transition-transform",
                          isExpanded && "rotate-90"
                        )}
                      />
                      Details
                    </Button>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      No details
                    </span>
                  )}
                </TableCell>
              </TableRow>
              {isExpanded && (
                <TableRow className="bg-muted/30 hover:bg-muted/30">
                  <TableCell colSpan={7} className="whitespace-normal p-3">
                    <div className="space-y-2">
                      {hasRelatedIds && <RelatedIds event={event} />}
                      {hasMetadata && (
                        <div className="space-y-2">
                          <div className="text-xs font-medium text-muted-foreground">
                            Metadata
                          </div>
                          <pre className="max-h-64 overflow-auto rounded-md bg-background px-3 py-2 font-mono text-xs">
                            {formatMetadata(event.metadata)}
                          </pre>
                        </div>
                      )}
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

function RelatedIds({ event }: { event: EventRecord }) {
  return (
    <div className="grid gap-2 text-xs md:grid-cols-3">
      <IdList label="Files" ids={event.file_ids} />
      <IdList label="Folders" ids={event.folder_ids} />
      <IdList label="Blobs" ids={event.blob_ids} />
    </div>
  )
}

function IdList({ label, ids }: { label: string; ids: string[] }) {
  if (ids.length === 0) return null

  return (
    <div className="space-y-1">
      <div className="font-medium text-muted-foreground">{label}</div>
      <div className="space-y-1 font-mono">
        {ids.map((id) => (
          <div key={id} className="break-all rounded bg-background px-2 py-1">
            {id}
          </div>
        ))}
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: EventRecord["status"] }) {
  return (
    <Badge variant={status === "succeeded" ? "secondary" : "destructive"}>
      {status}
    </Badge>
  )
}

function RelatedCounts({ event }: { event: EventRecord }) {
  const parts = [
    countLabel(event.file_ids.length, "file"),
    countLabel(event.folder_ids.length, "folder"),
    countLabel(event.blob_ids.length, "blob"),
  ].filter(Boolean)

  if (parts.length === 0) {
    return <span className="text-xs text-muted-foreground">None</span>
  }

  return (
    <div className="flex flex-wrap gap-1">
      {parts.map((part) => (
        <Badge key={part} variant="outline">
          {part}
        </Badge>
      ))}
    </div>
  )
}

function countLabel(count: number, label: string) {
  if (count === 0) return null
  return `${count} ${count === 1 ? label : `${label}s`}`
}

function formatMetadata(metadata: Record<string, unknown>) {
  if (Object.keys(metadata).length === 0) {
    return "{}"
  }
  return JSON.stringify(metadata, null, 2)
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value))
}
