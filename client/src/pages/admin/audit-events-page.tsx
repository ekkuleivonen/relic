import * as React from "react"
import { RefreshCw, X } from "lucide-react"

import { AuditEventDetailDrawer } from "@/components/audit-events/audit-event-detail-drawer"
import { AuditEventsTable } from "@/components/audit-events/audit-events-table"
import { OffsetPaginationBar } from "@/components/pagination-offset"
import { DateFilterPicker } from "@/components/filters/date-filter-picker"
import { FilterFieldLabel } from "@/components/filters/filter-field-label"
import { StringOptionCombobox } from "@/components/filters/string-option-combobox"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import {
  AUDIT_EVENTS_PAGE_SIZE,
  useAuditEvents,
} from "@/hooks/use-audit-events"
import { useDebouncedValue } from "@/hooks/use-debounced-value"
import { extractApiError } from "@/lib/api"
import { toEndOfDayIso, toStartOfDayIso } from "@/lib/date-filter"
import type {
  AuditEventRecord,
  AuditEventsQuery,
  AuditEventStatus,
} from "@/types/audit-events"
import {
  AUDIT_JOB_OPTIONS,
  AUDIT_OPERATION_OPTIONS,
  AUDIT_STATUS_OPTIONS,
} from "@/types/audit-events"

const TEXT_FILTER_DEBOUNCE_MS = 400

export function AuditEventsPage() {
  const [operation, setOperation] = React.useState<string | undefined>()
  const [status, setStatus] = React.useState<AuditEventStatus | undefined>()
  const [job, setJob] = React.useState<string | undefined>()
  const [requestIdInput, setRequestIdInput] = React.useState("")
  const [actorIdInput, setActorIdInput] = React.useState("")
  const [batchIdInput, setBatchIdInput] = React.useState("")
  const [storageBackendIdInput, setStorageBackendIdInput] = React.useState("")
  const [blobIdInput, setBlobIdInput] = React.useState("")
  const [createdAfter, setCreatedAfter] = React.useState<Date | undefined>()
  const [createdBefore, setCreatedBefore] = React.useState<Date | undefined>()
  const [offset, setOffset] = React.useState(0)
  const [selectedEvent, setSelectedEvent] =
    React.useState<AuditEventRecord | null>(null)

  const debouncedRequestId = useDebouncedValue(
    requestIdInput,
    TEXT_FILTER_DEBOUNCE_MS
  )
  const debouncedActorId = useDebouncedValue(actorIdInput, TEXT_FILTER_DEBOUNCE_MS)
  const debouncedBatchId = useDebouncedValue(batchIdInput, TEXT_FILTER_DEBOUNCE_MS)
  const debouncedStorageBackendId = useDebouncedValue(
    storageBackendIdInput,
    TEXT_FILTER_DEBOUNCE_MS
  )
  const debouncedBlobId = useDebouncedValue(blobIdInput, TEXT_FILTER_DEBOUNCE_MS)

  const filterParams = React.useMemo<Omit<AuditEventsQuery, "limit" | "offset">>(
    () => ({
      operation,
      status,
      job,
      request_id: trimOrUndefined(debouncedRequestId),
      actor_id: trimOrUndefined(debouncedActorId),
      batch_id: trimOrUndefined(debouncedBatchId),
      storage_backend_id: trimOrUndefined(debouncedStorageBackendId),
      blob_id: trimOrUndefined(debouncedBlobId),
      created_after: toStartOfDayIso(createdAfter),
      created_before: toEndOfDayIso(createdBefore),
    }),
    [
      operation,
      status,
      job,
      debouncedRequestId,
      debouncedActorId,
      debouncedBatchId,
      debouncedStorageBackendId,
      debouncedBlobId,
      createdAfter,
      createdBefore,
    ]
  )

  /* Pagination resets when debounced filters change; syncing via effect is intentional. */
  /* eslint-disable react-hooks/set-state-in-effect -- see comment above */
  React.useEffect(() => {
    setOffset(0)
    setSelectedEvent(null)
  }, [filterParams])
  /* eslint-enable react-hooks/set-state-in-effect */

  const filters = React.useMemo<AuditEventsQuery>(
    () => ({
      ...filterParams,
      limit: AUDIT_EVENTS_PAGE_SIZE,
      offset,
    }),
    [filterParams, offset]
  )

  const auditEventsQuery = useAuditEvents(filters)

  const hasActiveFilters =
    operation !== undefined ||
    status !== undefined ||
    job !== undefined ||
    requestIdInput !== "" ||
    actorIdInput !== "" ||
    batchIdInput !== "" ||
    storageBackendIdInput !== "" ||
    blobIdInput !== "" ||
    createdAfter !== undefined ||
    createdBefore !== undefined

  function resetFilters() {
    setOperation(undefined)
    setStatus(undefined)
    setJob(undefined)
    setRequestIdInput("")
    setActorIdInput("")
    setBatchIdInput("")
    setStorageBackendIdInput("")
    setBlobIdInput("")
    setCreatedAfter(undefined)
    setCreatedBefore(undefined)
    setOffset(0)
    setSelectedEvent(null)
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
          <Button
            type="button"
            variant="outline"
            size="sm"
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
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div className="grid gap-2">
              <FilterFieldLabel
                label="Operation"
                tooltip="Filter by audit operation name, such as auth.login.succeeded or blob.promoted."
              />
              <StringOptionCombobox
                options={AUDIT_OPERATION_OPTIONS}
                value={operation}
                onChange={setOperation}
                placeholder="Any operation"
                clearLabel="Any operation"
                searchPlaceholder="Search operations..."
                mono
              />
            </div>
            <div className="grid gap-2">
              <FilterFieldLabel
                label="Status"
                tooltip="Outcome of the audited action or maintenance run."
              />
              <StringOptionCombobox
                options={AUDIT_STATUS_OPTIONS}
                value={status}
                onChange={(value) =>
                  setStatus(value as AuditEventStatus | undefined)
                }
                placeholder="Any status"
                clearLabel="Any status"
                searchPlaceholder="Search status..."
              />
            </div>
            <div className="grid gap-2">
              <FilterFieldLabel
                label="Job"
                tooltip="Maintenance or background worker job that emitted the event."
              />
              <StringOptionCombobox
                options={AUDIT_JOB_OPTIONS}
                value={job}
                onChange={setJob}
                placeholder="Any job"
                clearLabel="Any job"
                searchPlaceholder="Search jobs..."
                mono
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="grid gap-2">
              <FilterFieldLabel
                label="Created after"
                tooltip="Include events on or after the start of this day."
              />
              <DateFilterPicker
                label="Pick a start date"
                value={createdAfter}
                onChange={setCreatedAfter}
              />
            </div>
            <div className="grid gap-2">
              <FilterFieldLabel
                label="Created before"
                tooltip="Include events on or before the end of this day."
              />
              <DateFilterPicker
                label="Pick an end date"
                value={createdBefore}
                onChange={setCreatedBefore}
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            <div className="grid gap-2">
              <FilterFieldLabel
                htmlFor="request-id"
                label="Request ID"
                tooltip="Correlate with X-Request-ID from an API call."
              />
              <Input
                id="request-id"
                className="h-9 font-mono text-xs"
                placeholder="Optional"
                value={requestIdInput}
                onChange={(event) => setRequestIdInput(event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <FilterFieldLabel
                htmlFor="batch-id"
                label="Batch ID"
                tooltip="Group identifier for batched maintenance work."
              />
              <Input
                id="batch-id"
                className="h-9 font-mono text-xs"
                placeholder="Optional"
                value={batchIdInput}
                onChange={(event) => setBatchIdInput(event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <FilterFieldLabel
                htmlFor="actor-id"
                label="Actor ID"
                tooltip="User UUID for human-initiated actions."
              />
              <Input
                id="actor-id"
                className="h-9 font-mono text-xs"
                placeholder="Optional"
                value={actorIdInput}
                onChange={(event) => setActorIdInput(event.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <FilterFieldLabel
                htmlFor="storage-backend-id"
                label="Storage backend ID"
                tooltip="Filter events tied to a specific storage backend."
              />
              <Input
                id="storage-backend-id"
                className="h-9 font-mono text-xs"
                placeholder="Optional"
                value={storageBackendIdInput}
                onChange={(event) =>
                  setStorageBackendIdInput(event.target.value)
                }
              />
            </div>
            <div className="grid gap-2">
              <FilterFieldLabel
                htmlFor="blob-id"
                label="Blob ID"
                tooltip="Filter events tied to a specific blob."
              />
              <Input
                id="blob-id"
                className="h-9 font-mono text-xs"
                placeholder="Optional"
                value={blobIdInput}
                onChange={(event) => setBlobIdInput(event.target.value)}
              />
            </div>
          </div>

          {hasActiveFilters && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={resetFilters}
            >
              <X className="size-4" />
              Reset filters
            </Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-2 sm:flex sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base">Audit Events</CardTitle>
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
                selectedEventId={selectedEvent?.id}
                onSelectEvent={setSelectedEvent}
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

      <AuditEventDetailDrawer
        event={selectedEvent}
        open={selectedEvent !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedEvent(null)
          }
        }}
      />
    </div>
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

function trimOrUndefined(value: string) {
  const trimmed = value.trim()
  return trimmed || undefined
}
