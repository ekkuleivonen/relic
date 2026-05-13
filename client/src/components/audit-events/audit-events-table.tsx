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
import type { AuditEventRecord } from "@/types/audit-events"

type AuditEventsTableProps = {
  auditEvents: AuditEventRecord[]
  isLoading: boolean
}

export function AuditEventsTable({
  auditEvents,
  isLoading,
}: AuditEventsTableProps) {
  const [expandedAuditEventIds, setExpandedAuditEventIds] = React.useState<
    Set<string>
  >(() => new Set())

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

  function toggleExpanded(auditEventId: string) {
    setExpandedAuditEventIds((current) => {
      const next = new Set(current)

      if (next.has(auditEventId)) {
        next.delete(auditEventId)
      } else {
        next.add(auditEventId)
      }

      return next
    })
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Time</TableHead>
          <TableHead>Audit Event</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Actor</TableHead>
          <TableHead>Request</TableHead>
          <TableHead className="text-right">Details</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {auditEvents.map((auditEvent) => {
          const isExpanded = expandedAuditEventIds.has(auditEvent.id)
          const hasMetadata = Object.keys(auditEvent.metadata).length > 0

          return (
            <React.Fragment key={auditEvent.id}>
              <TableRow>
                <TableCell className="whitespace-nowrap text-xs">
                  {formatDate(auditEvent.created_at)}
                </TableCell>
                <TableCell>
                  <div className="font-medium">{auditEvent.operation}</div>
                </TableCell>
                <TableCell>
                  <StatusBadge status={auditEvent.status} />
                </TableCell>
                <TableCell>
                  {auditEvent.actor ? (
                    <div className="space-y-1">
                      <div className="text-sm">{auditEvent.actor.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {auditEvent.actor.email}
                      </div>
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      System
                    </span>
                  )}
                </TableCell>
                <TableCell className="max-w-48 truncate font-mono text-xs">
                  {auditEvent.request_id ?? "—"}
                </TableCell>
                <TableCell className="text-right">
                  {hasMetadata ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-expanded={isExpanded}
                      onClick={() => toggleExpanded(auditEvent.id)}
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
              {isExpanded && hasMetadata && (
                <TableRow className="bg-muted/30 hover:bg-muted/30">
                  <TableCell colSpan={6} className="whitespace-normal p-3">
                    <div className="space-y-2">
                      <div className="text-xs font-medium text-muted-foreground">
                        Metadata
                      </div>
                      <pre className="max-h-64 overflow-auto rounded-md bg-background px-3 py-2 font-mono text-xs">
                        {formatMetadata(auditEvent.metadata)}
                      </pre>
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

function StatusBadge({ status }: { status: AuditEventRecord["status"] }) {
  return (
    <Badge variant={status === "succeeded" ? "secondary" : "destructive"}>
      {status}
    </Badge>
  )
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
