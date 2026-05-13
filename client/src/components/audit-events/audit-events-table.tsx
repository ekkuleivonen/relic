import * as React from "react"
import { ChevronRight } from "lucide-react"
import { Link } from "react-router"

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
          <TableHead>Related</TableHead>
          <TableHead className="text-right">Details</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {auditEvents.map((auditEvent) => {
          const isExpanded = expandedAuditEventIds.has(auditEvent.id)
          const hasMetadata = Object.keys(auditEvent.metadata).length > 0
          const hasRelatedIds =
            auditEvent.file_ids.length > 0 || auditEvent.folder_ids.length > 0
          const hasDetails = hasMetadata || hasRelatedIds

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
                <TableCell>
                  <RelatedCounts auditEvent={auditEvent} />
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
                  <TableCell colSpan={7} className="whitespace-normal p-3">
                    <div className="space-y-2">
                      {hasRelatedIds && <RelatedIds auditEvent={auditEvent} />}
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

function RelatedIds({ auditEvent }: { auditEvent: AuditEventRecord }) {
  return (
    <div className="grid gap-2 text-xs md:grid-cols-2">
      <IdList
        label="Files"
        ids={auditEvent.file_ids}
        buildHref={buildFileHref}
      />
      <IdList
        label="Folders"
        ids={auditEvent.folder_ids}
        buildHref={buildFolderHref}
      />
    </div>
  )
}

function IdList({
  label,
  ids,
  buildHref,
}: {
  label: string
  ids: string[]
  buildHref: (id: string) => string
}) {
  if (ids.length === 0) return null

  return (
    <div className="space-y-1">
      <div className="font-medium text-muted-foreground">{label}</div>
      <div className="space-y-1 font-mono">
        {ids.map((id) => (
          <Link
            key={id}
            to={buildHref(id)}
            className="block break-all rounded bg-background px-2 py-1 hover:text-primary hover:underline"
          >
            {id}
          </Link>
        ))}
      </div>
    </div>
  )
}

function StatusBadge({ status }: { status: AuditEventRecord["status"] }) {
  return (
    <Badge variant={status === "succeeded" ? "secondary" : "destructive"}>
      {status}
    </Badge>
  )
}

function RelatedCounts({ auditEvent }: { auditEvent: AuditEventRecord }) {
  const parts = [
    relatedCount(auditEvent.file_ids, "file", buildFileHref),
    relatedCount(auditEvent.folder_ids, "folder", buildFolderHref),
  ].filter(isRelatedCount)

  if (parts.length === 0) {
    return <span className="text-xs text-muted-foreground">None</span>
  }

  return (
    <div className="flex flex-wrap gap-1">
      {parts.map((part) => (
        <RelatedCountBadge key={part.label} part={part} />
      ))}
    </div>
  )
}

type RelatedCount = {
  label: string
  href: string | null
}

function isRelatedCount(part: RelatedCount | null): part is RelatedCount {
  return part !== null
}

function RelatedCountBadge({ part }: { part: RelatedCount }) {
  if (part.href) {
    return (
      <Badge variant="outline" asChild>
        <Link to={part.href}>{part.label}</Link>
      </Badge>
    )
  }

  return <Badge variant="outline">{part.label}</Badge>
}

function relatedCount(
  ids: string[],
  label: string,
  buildHref: (id: string) => string
): RelatedCount | null {
  const count = ids.length
  if (count === 0) return null
  return {
    label: `${count} ${count === 1 ? label : `${label}s`}`,
    href: count === 1 ? buildHref(ids[0]) : null,
  }
}

function buildFileHref(id: string) {
  return `/file/${encodeURIComponent(id)}`
}

function buildFolderHref(id: string) {
  return `/folder/${encodeURIComponent(id)}`
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
