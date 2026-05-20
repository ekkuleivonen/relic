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
  const [expandedIds, setExpandedIds] = React.useState<Set<string>>(
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

  if (auditEvents.length === 0) {
    return (
      <div className="border px-4 py-10 text-center text-sm text-muted-foreground">
        No audit events match these filters.
      </div>
    )
  }

  function toggleExpanded(eventId: string) {
    setExpandedIds((current) => {
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
          <TableHead>Operation</TableHead>
          <TableHead>Job</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Actor</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead>Batch</TableHead>
          <TableHead>Resource</TableHead>
          <TableHead className="text-right">Details</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {auditEvents.map((auditEvent) => {
          const isExpanded = expandedIds.has(auditEvent.id)
          const hasMetadata = Object.keys(auditEvent.metadata).length > 0
          const hasResourceIds = Boolean(
            auditEvent.storage_backend_id || auditEvent.blob_id
          )
          const hasDetails =
            hasMetadata || hasResourceIds || Boolean(auditEvent.request_id)

          return (
            <React.Fragment key={auditEvent.id}>
              <TableRow>
                <TableCell className="whitespace-nowrap text-xs">
                  {formatDate(auditEvent.created_at)}
                </TableCell>
                <TableCell>
                  <div className="font-medium">{auditEvent.operation}</div>
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {auditEvent.job ?? "—"}
                </TableCell>
                <TableCell>
                  <StatusBadge status={auditEvent.status} />
                </TableCell>
                <TableCell>
                  {auditEvent.actor ? (
                    <ActorCell auditEvent={auditEvent} />
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      System
                    </span>
                  )}
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs">
                  {auditEvent.duration_ms === null
                    ? "—"
                    : `${auditEvent.duration_ms} ms`}
                </TableCell>
                <TableCell className="max-w-40 truncate font-mono text-xs">
                  {auditEvent.batch_id ?? "—"}
                </TableCell>
                <TableCell>
                  <ResourceBadges auditEvent={auditEvent} />
                </TableCell>
                <TableCell className="text-right">
                  {hasDetails ? (
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
              {isExpanded && (
                <TableRow className="bg-muted/30 hover:bg-muted/30">
                  <TableCell colSpan={9} className="whitespace-normal p-3">
                    <div className="space-y-2">
                      {auditEvent.request_id && (
                        <div className="space-y-1 text-xs">
                          <div className="font-medium text-muted-foreground">
                            Request
                          </div>
                          <div className="break-all rounded bg-background px-2 py-1 font-mono">
                            {auditEvent.request_id}
                          </div>
                        </div>
                      )}
                      {hasResourceIds && (
                        <ResourceIds auditEvent={auditEvent} />
                      )}
                      {hasMetadata && (
                        <div className="space-y-2">
                          <div className="text-xs font-medium text-muted-foreground">
                            Metadata
                          </div>
                          <pre className="max-h-64 overflow-auto rounded-md bg-background px-3 py-2 font-mono text-xs">
                            {formatMetadata(auditEvent.metadata)}
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

function ActorCell({ auditEvent }: { auditEvent: AuditEventRecord }) {
  return (
    <div className="space-y-1">
      <div className="text-sm">{auditEvent.actor?.name}</div>
      <div className="text-xs text-muted-foreground">{auditEvent.actor?.email}</div>
    </div>
  )
}

function ResourceBadges({
  auditEvent,
}: {
  auditEvent: AuditEventRecord
}) {
  const parts = [
    auditEvent.storage_backend_id ? "storage backend" : null,
    auditEvent.blob_id ? "blob" : null,
  ].filter(isString)

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

function ResourceIds({
  auditEvent,
}: {
  auditEvent: AuditEventRecord
}) {
  return (
    <div className="grid gap-2 text-xs md:grid-cols-2">
      <IdBlock label="Storage backend" id={auditEvent.storage_backend_id} />
      <IdBlock label="Blob" id={auditEvent.blob_id} />
    </div>
  )
}

function IdBlock({ label, id }: { label: string; id: string | null }) {
  if (!id) return null

  return (
    <div className="space-y-1">
      <div className="font-medium text-muted-foreground">{label}</div>
      <div className="break-all rounded bg-background px-2 py-1 font-mono">
        {id}
      </div>
    </div>
  )
}

function StatusBadge({
  status,
}: {
  status: AuditEventRecord["status"]
}) {
  if (status === "failed") {
    return <Badge variant="destructive">{status}</Badge>
  }

  if (status === "skipped") {
    return <Badge variant="outline">{status}</Badge>
  }

  return <Badge variant="secondary">{status}</Badge>
}

function isString(value: string | null): value is string {
  return value !== null
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
