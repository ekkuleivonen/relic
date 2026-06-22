import { ChevronRight } from "lucide-react"

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
import { cn } from "@/lib/utils"
import type { FilesystemEventRecord } from "@/types/filesystem-events"

type FilesystemEventsTableProps = {
  events: FilesystemEventRecord[]
  isLoading: boolean
  selectedEventId?: string
  onSelectEvent: (event: FilesystemEventRecord) => void
}

export function FilesystemEventsTable({
  events,
  isLoading,
  selectedEventId,
  onSelectEvent,
}: FilesystemEventsTableProps) {
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
        No filesystem events match these filters.
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Seq</TableHead>
          <TableHead>Time</TableHead>
          <TableHead>Type</TableHead>
          <TableHead>Folder</TableHead>
          <TableHead>File</TableHead>
          <TableHead>Actor</TableHead>
          <TableHead className="w-10" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map((event) => {
          const isSelected = event.id === selectedEventId

          return (
            <TableRow
              key={event.id}
              data-state={isSelected ? "selected" : undefined}
              className={cn(
                "cursor-pointer",
                isSelected && "bg-muted/50"
              )}
              onClick={() => onSelectEvent(event)}
            >
              <TableCell className="font-mono text-xs">{event.seq}</TableCell>
              <TableCell className="whitespace-nowrap text-xs">
                {formatDate(event.created_at)}
              </TableCell>
              <TableCell>
                <Badge variant="outline">{event.event_type}</Badge>
              </TableCell>
              <TableCell className="max-w-36 truncate font-mono text-xs">
                {event.folder_id}
              </TableCell>
              <TableCell className="max-w-36 truncate font-mono text-xs">
                {event.file_id ?? "—"}
              </TableCell>
              <TableCell className="max-w-36 truncate font-mono text-xs">
                {event.actor_id ?? "—"}
              </TableCell>
              <TableCell className="text-muted-foreground">
                <ChevronRight className="size-4" />
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value))
}
