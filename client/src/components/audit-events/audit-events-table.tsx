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
import type { AuditEventRecord } from "@/types/audit-events"

type AuditEventsTableProps = {
  auditEvents: AuditEventRecord[]
  isLoading: boolean
  selectedEventId?: string
  onSelectEvent: (event: AuditEventRecord) => void
}

export function AuditEventsTable({
  auditEvents,
  isLoading,
  selectedEventId,
  onSelectEvent,
}: AuditEventsTableProps) {
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

  if (auditEvents.length === 0) {
    return (
      <div className="border px-4 py-10 text-center text-sm text-muted-foreground">
        No audit events match these filters.
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>Operation</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Actor</TableHead>
          <TableHead>Job</TableHead>
          <TableHead className="w-10" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {auditEvents.map((auditEvent) => {
          const isSelected = auditEvent.id === selectedEventId

          return (
            <TableRow
              key={auditEvent.id}
              data-state={isSelected ? "selected" : undefined}
              className={cn("cursor-pointer", isSelected && "bg-muted/50")}
              onClick={() => onSelectEvent(auditEvent)}
            >
              <TableCell className="whitespace-nowrap text-xs">
                {formatDate(auditEvent.created_at)}
              </TableCell>
              <TableCell className="max-w-48 truncate font-medium">
                {auditEvent.operation}
              </TableCell>
              <TableCell>
                <StatusBadge status={auditEvent.status} />
              </TableCell>
              <TableCell className="max-w-40 truncate text-xs">
                {auditEvent.actor ? auditEvent.actor.name : "System"}
              </TableCell>
              <TableCell className="max-w-40 truncate font-mono text-xs text-muted-foreground">
                {auditEvent.job ?? "—"}
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

function StatusBadge({ status }: { status: AuditEventRecord["status"] }) {
  if (status === "failed") {
    return <Badge variant="destructive">{status}</Badge>
  }

  if (status === "skipped") {
    return <Badge variant="outline">{status}</Badge>
  }

  return <Badge variant="secondary">{status}</Badge>
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value))
}
