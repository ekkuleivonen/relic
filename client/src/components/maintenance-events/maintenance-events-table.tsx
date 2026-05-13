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
import type { MaintenanceEventRecord } from "@/types/maintenance-events"

type MaintenanceEventsTableProps = {
  maintenanceEvents: MaintenanceEventRecord[]
  isLoading: boolean
}

export function MaintenanceEventsTable({
  maintenanceEvents,
  isLoading,
}: MaintenanceEventsTableProps) {
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

  if (maintenanceEvents.length === 0) {
    return (
      <div className="border px-4 py-10 text-center text-sm text-muted-foreground">
        No maintenance events match these filters.
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
          <TableHead>Job</TableHead>
          <TableHead>Action</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Duration</TableHead>
          <TableHead>Batch</TableHead>
          <TableHead>Resource</TableHead>
          <TableHead className="text-right">Details</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {maintenanceEvents.map((maintenanceEvent) => {
          const isExpanded = expandedIds.has(maintenanceEvent.id)
          const hasMetadata = Object.keys(maintenanceEvent.metadata).length > 0
          const hasResourceIds = Boolean(
            maintenanceEvent.bucket_id || maintenanceEvent.blob_id
          )
          const hasDetails = hasMetadata || hasResourceIds

          return (
            <React.Fragment key={maintenanceEvent.id}>
              <TableRow>
                <TableCell className="whitespace-nowrap text-xs">
                  {formatDate(maintenanceEvent.created_at)}
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {maintenanceEvent.job}
                </TableCell>
                <TableCell>
                  <div className="font-medium">{maintenanceEvent.action}</div>
                </TableCell>
                <TableCell>
                  <StatusBadge status={maintenanceEvent.status} />
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs">
                  {maintenanceEvent.duration_ms === null
                    ? "—"
                    : `${maintenanceEvent.duration_ms} ms`}
                </TableCell>
                <TableCell className="max-w-40 truncate font-mono text-xs">
                  {maintenanceEvent.batch_id}
                </TableCell>
                <TableCell>
                  <ResourceBadges maintenanceEvent={maintenanceEvent} />
                </TableCell>
                <TableCell className="text-right">
                  {hasDetails ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-expanded={isExpanded}
                      onClick={() => toggleExpanded(maintenanceEvent.id)}
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
                  <TableCell colSpan={8} className="whitespace-normal p-3">
                    <div className="space-y-2">
                      {hasResourceIds && (
                        <ResourceIds maintenanceEvent={maintenanceEvent} />
                      )}
                      {hasMetadata && (
                        <div className="space-y-2">
                          <div className="text-xs font-medium text-muted-foreground">
                            Metadata
                          </div>
                          <pre className="max-h-64 overflow-auto rounded-md bg-background px-3 py-2 font-mono text-xs">
                            {formatMetadata(maintenanceEvent.metadata)}
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

function ResourceBadges({
  maintenanceEvent,
}: {
  maintenanceEvent: MaintenanceEventRecord
}) {
  const parts = [
    maintenanceEvent.bucket_id ? "bucket" : null,
    maintenanceEvent.blob_id ? "blob" : null,
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
  maintenanceEvent,
}: {
  maintenanceEvent: MaintenanceEventRecord
}) {
  return (
    <div className="grid gap-2 text-xs md:grid-cols-2">
      <IdBlock label="Bucket" id={maintenanceEvent.bucket_id} />
      <IdBlock label="Blob" id={maintenanceEvent.blob_id} />
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
  status: MaintenanceEventRecord["status"]
}) {
  if (status === "failed") {
    return <Badge variant="destructive">{status}</Badge>
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
