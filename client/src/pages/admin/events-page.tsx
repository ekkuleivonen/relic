import * as React from "react"
import { CalendarIcon, RefreshCw, Search, Trash2, X } from "lucide-react"

import { EventsTable } from "@/components/events/events-table"
import { OffsetPaginationBar } from "@/components/pagination-offset"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Calendar } from "@/components/ui/calendar"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { EVENTS_PAGE_SIZE, useClearEvents, useEvents } from "@/hooks/use-events"
import { extractApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { EventStatus, EventsQuery } from "@/types/events"

const STATUS_ALL = "all"
const SOURCE_ALL = "all"
const OPERATION_ALL = "all"

const SOURCE_OPTIONS = [
  { value: "relic_api", label: "Relic API" },
  { value: "s3_gateway", label: "S3 gateway" },
  { value: "processor", label: "Processor" },
  { value: "maintenance", label: "Maintenance" },
] as const

const OPERATIONS_BY_SOURCE = {
  relic_api: [
    "access_key.created",
    "access_key.deleted",
    "access_key.revoked",
    "auth.login.failed",
    "auth.login.succeeded",
    "auth.logout",
    "bucket.created",
    "bucket.deleted",
    "bucket.probed",
    "bucket.updated",
    "file.moved",
    "file.renamed",
    "folder.access.granted",
    "folder.access.revoked",
    "folder.access.updated",
    "folder.copied",
    "folder.created",
    "folder.deleted",
    "folder.updated",
    "presign.copy.created",
    "presign.delete.created",
    "presign.download.created",
    "presign.upload.created",
    "user.created",
    "user.deleted",
    "user.updated",
  ],
  s3_gateway: [
    "object.copied",
    "object.deleted",
    "object.get",
    "object.head",
    "object.put",
  ],
  processor: ["file.metadata.updated", "parse.failed"],
  maintenance: ["blob.migrated", "blob.purged", "bucket.probed"],
} as const

const OPERATION_OPTIONS = Array.from(
  new Set(Object.values(OPERATIONS_BY_SOURCE).flat())
).sort()

type EventFiltersDraft = {
  source: string
  operation: string
  status: string
  actor_user_id: string
  request_id: string
  created_after: Date | undefined
  created_before: Date | undefined
}

export function EventsPage() {
  const [filters, setFilters] = React.useState<EventsQuery>({
    limit: EVENTS_PAGE_SIZE,
    offset: 0,
  })
  const [clearDialogOpen, setClearDialogOpen] = React.useState(false)
  const [draft, setDraft] = React.useState<EventFiltersDraft>({
    source: SOURCE_ALL,
    operation: OPERATION_ALL,
    status: STATUS_ALL,
    actor_user_id: "",
    request_id: "",
    created_after: undefined,
    created_before: undefined,
  })
  const eventsQuery = useEvents(filters)
  const clearEventsMutation = useClearEvents()
  const operationOptions = operationsForSource(draft.source)

  function applyFilters(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFilters({
      source: draft.source === SOURCE_ALL ? undefined : draft.source,
      operation:
        draft.operation === OPERATION_ALL ? undefined : draft.operation,
      status:
        draft.status === STATUS_ALL ? undefined : (draft.status as EventStatus),
      actor_user_id: draft.actor_user_id,
      request_id: draft.request_id,
      created_after: toStartOfDayIso(draft.created_after),
      created_before: toEndOfDayIso(draft.created_before),
      limit: EVENTS_PAGE_SIZE,
      offset: 0,
    })
  }

  function clearFilters() {
    setDraft({
      source: SOURCE_ALL,
      operation: OPERATION_ALL,
      status: STATUS_ALL,
      actor_user_id: "",
      request_id: "",
      created_after: undefined,
      created_before: undefined,
    })
    setFilters({ limit: EVENTS_PAGE_SIZE, offset: 0 })
  }

  function setOffset(offset: number) {
    setFilters((current) => ({ ...current, offset }))
  }

  async function clearAuditLog() {
    try {
      await clearEventsMutation.mutateAsync()
      setFilters({ limit: EVENTS_PAGE_SIZE, offset: 0 })
      setClearDialogOpen(false)
    } catch {
      // Error toast is handled by the mutation hook.
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Audit Log</h1>
          <p className="text-sm text-muted-foreground">
            Explore durable system events across the S3 gateway, API, and
            background processors.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <AlertDialog
            open={clearDialogOpen}
            onOpenChange={setClearDialogOpen}
          >
            <AlertDialogTrigger asChild>
              <Button
                type="button"
                variant="destructive"
                disabled={clearEventsMutation.isPending}
              >
                <Trash2 />
                Clear Audit Log
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Clear the audit log?</AlertDialogTitle>
                <AlertDialogDescription>
                  This permanently deletes every event from the audit log. New
                  events will continue to be recorded after the table is cleared.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={clearEventsMutation.isPending}>
                  Cancel
                </AlertDialogCancel>
                <AlertDialogAction
                  variant="destructive"
                  disabled={clearEventsMutation.isPending}
                  onClick={(event) => {
                    event.preventDefault()
                    void clearAuditLog()
                  }}
                >
                  {clearEventsMutation.isPending ? "Clearing..." : "Clear"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <Button
            type="button"
            variant="outline"
            onClick={() => void eventsQuery.refetch()}
            disabled={eventsQuery.isFetching}
          >
            <RefreshCw
              className={eventsQuery.isFetching ? "animate-spin" : ""}
            />
            Refresh
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 lg:grid-cols-6" onSubmit={applyFilters}>
            <Select
              value={draft.source}
              onValueChange={(source) =>
                setDraft((current) => ({
                  ...current,
                  source,
                  operation: operationBelongsToSource(
                    current.operation,
                    source
                  )
                    ? current.operation
                    : OPERATION_ALL,
                }))
              }
            >
              <SelectTrigger className="h-9 w-full">
                <SelectValue placeholder="Source" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={SOURCE_ALL}>Any source</SelectItem>
                {SOURCE_OPTIONS.map((source) => (
                  <SelectItem key={source.value} value={source.value}>
                    {source.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={draft.operation}
              onValueChange={(operation) =>
                setDraft((current) => ({ ...current, operation }))
              }
            >
              <SelectTrigger className="h-9 w-full">
                <SelectValue placeholder="Operation" />
              </SelectTrigger>
              <SelectContent className="max-h-80">
                <SelectItem value={OPERATION_ALL}>Any operation</SelectItem>
                {operationOptions.map((operation) => (
                  <SelectItem key={operation} value={operation}>
                    {operation}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={draft.status}
              onValueChange={(status) =>
                setDraft((current) => ({ ...current, status }))
              }
            >
              <SelectTrigger className="h-9 w-full">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={STATUS_ALL}>Any status</SelectItem>
                <SelectItem value="succeeded">Succeeded</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
              </SelectContent>
            </Select>
            <Input
              placeholder="Request ID"
              value={draft.request_id}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  request_id: event.target.value,
                }))
              }
            />
            <Input
              placeholder="Actor user ID"
              value={draft.actor_user_id}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  actor_user_id: event.target.value,
                }))
              }
            />
            <div className="flex gap-2">
              <Button type="submit" className="flex-1">
                <Search />
                Apply
              </Button>
              <Button type="button" variant="outline" onClick={clearFilters}>
                <X />
                Clear
              </Button>
            </div>
            <DateFilterPicker
              label="Created after"
              value={draft.created_after}
              onChange={(date) =>
                setDraft((current) => ({
                  ...current,
                  created_after: date,
                }))
              }
            />
            <DateFilterPicker
              label="Created before"
              value={draft.created_before}
              onChange={(date) =>
                setDraft((current) => ({
                  ...current,
                  created_before: date,
                }))
              }
            />
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-2 sm:flex sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Events</CardTitle>
          {eventsQuery.data && (
            <div className="text-xs text-muted-foreground">
              {eventsQuery.data.total.toLocaleString()}{" "}
              {eventsQuery.data.total === 1 ? "event" : "events"}
            </div>
          )}
        </CardHeader>
        <CardContent>
          {eventsQuery.isError ? (
            <ErrorState
              message={extractApiError(eventsQuery.error)}
              onRetry={() => void eventsQuery.refetch()}
            />
          ) : (
            <>
              <EventsTable
                events={eventsQuery.data?.items ?? []}
                isLoading={eventsQuery.isLoading}
              />
              {eventsQuery.data && (
                <OffsetPaginationBar
                  total={eventsQuery.data.total}
                  limit={eventsQuery.data.limit}
                  offset={eventsQuery.data.offset}
                  onChange={setOffset}
                />
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function DateFilterPicker({
  label,
  value,
  onChange,
}: {
  label: string
  value: Date | undefined
  onChange: (date: Date | undefined) => void
}) {
  const [open, setOpen] = React.useState(false)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          className={cn(
            "h-9 w-full justify-start text-left font-normal",
            !value && "text-muted-foreground"
          )}
          aria-label={label}
        >
          <CalendarIcon />
          {value ? formatFilterDate(value) : label}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-0">
        <Calendar
          mode="single"
          selected={value}
          onSelect={(date) => {
            onChange(date)
            setOpen(false)
          }}
          captionLayout="dropdown"
        />
        <div className="border-t p-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="w-full"
            disabled={!value}
            onClick={() => onChange(undefined)}
          >
            Clear date
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function ErrorState({
  message,
  onRetry,
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div className="rounded-md border border-destructive/20 bg-destructive/5 p-4">
      <div className="font-medium text-destructive">Could not load events</div>
      <p className="mt-1 text-xs text-muted-foreground">{message}</p>
      <Button className="mt-3" type="button" variant="outline" onClick={onRetry}>
        <RefreshCw className="size-3.5" />
        Retry
      </Button>
    </div>
  )
}

function formatFilterDate(value: Date) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
  }).format(value)
}

function operationsForSource(source: string): string[] {
  if (source === SOURCE_ALL) {
    return OPERATION_OPTIONS
  }

  return [
    ...(OPERATIONS_BY_SOURCE[source as keyof typeof OPERATIONS_BY_SOURCE] ?? []),
  ]
}

function operationBelongsToSource(operation: string, source: string) {
  if (operation === OPERATION_ALL || source === SOURCE_ALL) {
    return true
  }

  return operationsForSource(source).includes(operation)
}

function toStartOfDayIso(value: Date | undefined) {
  if (!value) return undefined
  const date = new Date(value)
  date.setHours(0, 0, 0, 0)
  return date.toISOString()
}

function toEndOfDayIso(value: Date | undefined) {
  if (!value) return undefined
  const date = new Date(value)
  date.setHours(23, 59, 59, 999)
  return date.toISOString()
}
