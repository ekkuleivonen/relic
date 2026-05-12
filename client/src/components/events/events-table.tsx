import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { EventRecord } from "@/types/events"

type EventsTableProps = {
  events: EventRecord[]
  isLoading: boolean
}

export function EventsTable({ events, isLoading }: EventsTableProps) {
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
          <TableHead>Metadata</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map((event) => (
          <TableRow key={event.id}>
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
                <span className="text-xs text-muted-foreground">System</span>
              )}
            </TableCell>
            <TableCell className="max-w-48 truncate font-mono text-xs">
              {event.request_id ?? "—"}
            </TableCell>
            <TableCell>
              <RelatedCounts event={event} />
            </TableCell>
            <TableCell className="max-w-72">
              <pre className="max-h-24 overflow-auto rounded bg-muted px-2 py-1 text-xs">
                {formatMetadata(event.metadata)}
              </pre>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
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
