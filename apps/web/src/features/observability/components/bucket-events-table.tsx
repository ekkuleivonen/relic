import { Link } from "react-router"

import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { formatDate } from "@/features/job-runs/components/job-run-format"
import { BucketEventStateBadge } from "@/features/observability/components/bucket-event-state-badge"
import type { BucketEvent } from "@/types/bucket-events"

type BucketEventsTableProps = {
  events: BucketEvent[]
  bucketNames: Record<string, string>
}

export function BucketEventsTable({
  events,
  bucketNames,
}: BucketEventsTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Event</TableHead>
            <TableHead>Object key</TableHead>
            <TableHead>Bucket</TableHead>
            <TableHead>State</TableHead>
            <TableHead>Received</TableHead>
            <TableHead>Processed</TableHead>
            <TableHead className="w-24 text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {events.map((event) => (
            <TableRow key={event.id}>
              <TableCell>
                <div className="font-medium">{event.event_name}</div>
                <div className="mt-0.5 max-w-64 truncate font-mono text-[11px] text-muted-foreground">
                  {event.id}
                </div>
              </TableCell>
              <TableCell>
                <div className="max-w-64 truncate font-mono text-xs">
                  {event.object_key || "-"}
                </div>
              </TableCell>
              <TableCell>
                <div>{bucketNames[event.bucket_id] ?? "Bucket"}</div>
                <div className="mt-0.5 max-w-48 truncate font-mono text-[11px] text-muted-foreground">
                  {event.bucket_id}
                </div>
              </TableCell>
              <TableCell>
                <BucketEventStateBadge state={event.state} />
              </TableCell>
              <TableCell>{formatDate(event.received_at)}</TableCell>
              <TableCell>
                {event.processed_at ? formatDate(event.processed_at) : "-"}
              </TableCell>
              <TableCell>
                <div className="flex justify-end">
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={`/bucket-events/${event.id}`}>View</Link>
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
