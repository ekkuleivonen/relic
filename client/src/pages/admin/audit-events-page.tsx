import * as React from "react"
import { CalendarIcon, RefreshCw, Search, Trash2, X } from "lucide-react"

import { AuditEventsTable } from "@/components/audit-events/audit-events-table"
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
import {
  AUDIT_EVENTS_PAGE_SIZE,
  useAuditEvents,
  useClearAuditEvents,
} from "@/hooks/use-audit-events"
import { extractApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { AuditEventsQuery, AuditEventStatus } from "@/types/audit-events"

const STATUS_ALL = "all"
const OPERATION_ALL = "all"
const JOB_ALL = "all"

const JOB_OPTIONS = [
  "purge_dereferenced_blobs",
  "demote_pressured_buckets",
  "promote_recently_accessed",
  "bucket_probe",
  "trim_bucket_probes",
  "trim_audit_events",
  "abort_incomplete_multipart_uploads",
] as const

const OPERATION_OPTIONS = [
  "access_key.created",
  "access_key.deleted",
  "access_key.revoked",
  "audit_event.trimmed",
  "auth.login.failed",
  "auth.login.succeeded",
  "auth.logout",
  "blob.demoted",
  "blob.demotion_skipped",
  "blob.promoted",
  "blob.purged",
  "blob.purge_failed",
  "bucket.created",
  "bucket.deleted",
  "bucket.probe_failed",
  "bucket.updated",
  "bucket_probe.trimmed",
  "folder.access.granted",
  "folder.access.revoked",
  "folder.access.updated",
  "multipart_upload.aborted",
  "user.created",
  "user.deleted",
  "user.updated",
] as const

type AuditEventFiltersDraft = {
  operation: string
  job: string
  status: string
  actor_id: string
  request_id: string
  batch_id: string
  storage_backend_id: string
  blob_id: string
  created_after: Date | undefined
  created_before: Date | undefined
}

export function AuditEventsPage() {
  const [filters, setFilters] = React.useState<AuditEventsQuery>({
    limit: AUDIT_EVENTS_PAGE_SIZE,
    offset: 0,
  })
  const [clearDialogOpen, setClearDialogOpen] = React.useState(false)
  const [draft, setDraft] = React.useState<AuditEventFiltersDraft>({
    operation: OPERATION_ALL,
    job: JOB_ALL,
    status: STATUS_ALL,
    actor_id: "",
    request_id: "",
    batch_id: "",
    storage_backend_id: "",
    blob_id: "",
    created_after: undefined,
    created_before: undefined,
  })
  const auditEventsQuery = useAuditEvents(filters)
  const clearAuditEventsMutation = useClearAuditEvents()

  function applyFilters(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFilters({
      operation:
        draft.operation === OPERATION_ALL ? undefined : draft.operation,
      job: draft.job === JOB_ALL ? undefined : draft.job,
      status:
        draft.status === STATUS_ALL
          ? undefined
          : (draft.status as AuditEventStatus),
      actor_id: draft.actor_id,
      request_id: draft.request_id,
      batch_id: draft.batch_id,
      storage_backend_id: draft.storage_backend_id,
      blob_id: draft.blob_id,
      created_after: toStartOfDayIso(draft.created_after),
      created_before: toEndOfDayIso(draft.created_before),
      limit: AUDIT_EVENTS_PAGE_SIZE,
      offset: 0,
    })
  }

  function clearFilters() {
    setDraft({
      operation: OPERATION_ALL,
      job: JOB_ALL,
      status: STATUS_ALL,
      actor_id: "",
      request_id: "",
      batch_id: "",
      storage_backend_id: "",
      blob_id: "",
      created_after: undefined,
      created_before: undefined,
    })
    setFilters({ limit: AUDIT_EVENTS_PAGE_SIZE, offset: 0 })
  }

  function setOffset(offset: number) {
    setFilters((current) => ({ ...current, offset }))
  }

  async function clearAuditLog() {
    try {
      await clearAuditEventsMutation.mutateAsync()
      setFilters({ limit: AUDIT_EVENTS_PAGE_SIZE, offset: 0 })
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
            Explore durable audit events for identity, access, storage backend,
            folder changes, and storage maintenance.
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
                disabled={clearAuditEventsMutation.isPending}
              >
                <Trash2 />
                Clear Audit Log
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Clear the audit log?</AlertDialogTitle>
                <AlertDialogDescription>
                  This permanently deletes every audit event. New audit events
                  will continue to be recorded after the table is cleared.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel
                  disabled={clearAuditEventsMutation.isPending}
                >
                  Cancel
                </AlertDialogCancel>
                <AlertDialogAction
                  variant="destructive"
                  disabled={clearAuditEventsMutation.isPending}
                  onClick={(event) => {
                    event.preventDefault()
                    void clearAuditLog()
                  }}
                >
                  {clearAuditEventsMutation.isPending ? "Clearing..." : "Clear"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <Button
            type="button"
            variant="outline"
            onClick={() => void auditEventsQuery.refetch()}
            disabled={auditEventsQuery.isFetching}
          >
            <RefreshCw
              className={auditEventsQuery.isFetching ? "animate-spin" : ""}
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
          <form className="grid gap-3 lg:grid-cols-5" onSubmit={applyFilters}>
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
                {OPERATION_OPTIONS.map((operation) => (
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
                <SelectItem value="skipped">Skipped</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={draft.job}
              onValueChange={(job) =>
                setDraft((current) => ({ ...current, job }))
              }
            >
              <SelectTrigger className="h-9 w-full">
                <SelectValue placeholder="Job" />
              </SelectTrigger>
              <SelectContent className="max-h-80">
                <SelectItem value={JOB_ALL}>Any job</SelectItem>
                {JOB_OPTIONS.map((job) => (
                  <SelectItem key={job} value={job}>
                    {job}
                  </SelectItem>
                ))}
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
              placeholder="Actor ID"
              value={draft.actor_id}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  actor_id: event.target.value,
                }))
              }
            />
            <Input
              placeholder="Batch ID"
              value={draft.batch_id}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  batch_id: event.target.value,
                }))
              }
            />
            <Input
              placeholder="Storage Backend ID"
              value={draft.storage_backend_id}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  storage_backend_id: event.target.value,
                }))
              }
            />
            <Input
              placeholder="Blob ID"
              value={draft.blob_id}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  blob_id: event.target.value,
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
          <CardTitle>Audit Events</CardTitle>
          {auditEventsQuery.data && (
            <div className="text-xs text-muted-foreground">
              {auditEventsQuery.data.total.toLocaleString()}{" "}
              {auditEventsQuery.data.total === 1
                ? "audit event"
                : "audit events"}
            </div>
          )}
        </CardHeader>
        <CardContent>
          {auditEventsQuery.isError ? (
            <ErrorState
              message={extractApiError(auditEventsQuery.error)}
              onRetry={() => void auditEventsQuery.refetch()}
            />
          ) : (
            <>
              <AuditEventsTable
                auditEvents={auditEventsQuery.data?.items ?? []}
                isLoading={auditEventsQuery.isLoading}
              />
              {auditEventsQuery.data && (
                <OffsetPaginationBar
                  total={auditEventsQuery.data.total}
                  limit={auditEventsQuery.data.limit}
                  offset={auditEventsQuery.data.offset}
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
      <div className="font-medium text-destructive">
        Could not load audit events
      </div>
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
