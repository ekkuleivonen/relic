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
import type { FileEventRecord } from "@/types/file-events"

type FileEventsTableProps = {
  fileEvents: FileEventRecord[]
  isLoading: boolean
}

export function FileEventsTable({
  fileEvents,
  isLoading,
}: FileEventsTableProps) {
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

  if (fileEvents.length === 0) {
    return (
      <div className="border px-4 py-10 text-center text-sm text-muted-foreground">
        No file events match these filters.
      </div>
    )
  }

  function toggleExpanded(fileEventId: string) {
    setExpandedIds((current) => {
      const next = new Set(current)

      if (next.has(fileEventId)) {
        next.delete(fileEventId)
      } else {
        next.add(fileEventId)
      }

      return next
    })
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Offset</TableHead>
          <TableHead>Time</TableHead>
          <TableHead>File Event</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Actor</TableHead>
          <TableHead>Request</TableHead>
          <TableHead>Related</TableHead>
          <TableHead className="text-right">Details</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {fileEvents.map((fileEvent) => {
          const isExpanded = expandedIds.has(fileEvent.id)
          const hasPayload = Object.keys(fileEvent.payload).length > 0
          const hasRelatedIds = Boolean(fileEvent.file_id || fileEvent.folder_id)
          const hasDetails = hasPayload || hasRelatedIds

          return (
            <React.Fragment key={fileEvent.id}>
              <TableRow>
                <TableCell className="font-mono text-xs">
                  {fileEvent.offset}
                </TableCell>
                <TableCell className="whitespace-nowrap text-xs">
                  {formatDate(fileEvent.created_at)}
                </TableCell>
                <TableCell>
                  <div className="font-medium">{fileEvent.event_type}</div>
                  <div className="text-xs text-muted-foreground">
                    schema v{fileEvent.schema_version}
                  </div>
                </TableCell>
                <TableCell>
                  <StatusBadge status={fileEvent.status} />
                </TableCell>
                <TableCell>
                  {fileEvent.actor ? (
                    <div className="space-y-1">
                      <div className="text-sm">{fileEvent.actor.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {fileEvent.actor.email}
                      </div>
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      System
                    </span>
                  )}
                </TableCell>
                <TableCell className="max-w-48 truncate font-mono text-xs">
                  {fileEvent.request_id ?? "—"}
                </TableCell>
                <TableCell>
                  <RelatedLinks fileEvent={fileEvent} />
                </TableCell>
                <TableCell className="text-right">
                  {hasDetails ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      aria-expanded={isExpanded}
                      onClick={() => toggleExpanded(fileEvent.id)}
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
                      {hasRelatedIds && <RelatedIds fileEvent={fileEvent} />}
                      {hasPayload && (
                        <div className="space-y-2">
                          <div className="text-xs font-medium text-muted-foreground">
                            Payload
                          </div>
                          <pre className="max-h-64 overflow-auto rounded-md bg-background px-3 py-2 font-mono text-xs">
                            {formatPayload(fileEvent.payload)}
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

function RelatedLinks({ fileEvent }: { fileEvent: FileEventRecord }) {
  const parts = [
    relatedLink(fileEvent.file_id, "file", buildFileHref),
    relatedLink(fileEvent.folder_id, "folder", buildFolderHref),
  ].filter(isRelatedLink)

  if (parts.length === 0) {
    return <span className="text-xs text-muted-foreground">None</span>
  }

  return (
    <div className="flex flex-wrap gap-1">
      {parts.map((part) => (
        <Badge key={part.label} variant="outline" asChild>
          <Link to={part.href}>{part.label}</Link>
        </Badge>
      ))}
    </div>
  )
}

function RelatedIds({ fileEvent }: { fileEvent: FileEventRecord }) {
  return (
    <div className="grid gap-2 text-xs md:grid-cols-2">
      <IdLink label="File" id={fileEvent.file_id} buildHref={buildFileHref} />
      <IdLink
        label="Folder"
        id={fileEvent.folder_id}
        buildHref={buildFolderHref}
      />
    </div>
  )
}

function IdLink({
  label,
  id,
  buildHref,
}: {
  label: string
  id: string | null
  buildHref: (id: string) => string
}) {
  if (!id) return null

  return (
    <div className="space-y-1">
      <div className="font-medium text-muted-foreground">{label}</div>
      <Link
        to={buildHref(id)}
        className="block break-all rounded bg-background px-2 py-1 font-mono hover:text-primary hover:underline"
      >
        {id}
      </Link>
    </div>
  )
}

type RelatedLink = {
  label: string
  href: string
}

function isRelatedLink(part: RelatedLink | null): part is RelatedLink {
  return part !== null
}

function relatedLink(
  id: string | null,
  label: string,
  buildHref: (id: string) => string
): RelatedLink | null {
  if (!id) return null
  return { label, href: buildHref(id) }
}

function StatusBadge({ status }: { status: FileEventRecord["status"] }) {
  return (
    <Badge variant={status === "succeeded" ? "secondary" : "destructive"}>
      {status}
    </Badge>
  )
}

function buildFileHref(id: string) {
  return `/file/${encodeURIComponent(id)}`
}

function buildFolderHref(id: string) {
  return `/folder/${encodeURIComponent(id)}`
}

function formatPayload(payload: Record<string, unknown>) {
  if (Object.keys(payload).length === 0) {
    return "{}"
  }
  return JSON.stringify(payload, null, 2)
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value))
}
