import * as React from "react"
import { CalendarIcon, RefreshCw, Search, Trash2, X } from "lucide-react"

import { MaintenanceEventsTable } from "@/components/maintenance-events/maintenance-events-table"
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
  MAINTENANCE_EVENTS_PAGE_SIZE,
  useClearMaintenanceEvents,
  useMaintenanceEvents,
} from "@/hooks/use-maintenance-events"
import { extractApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import type {
  MaintenanceEventsQuery,
  MaintenanceEventStatus,
} from "@/types/maintenance-events"

const STATUS_ALL = "all"
const JOB_ALL = "all"
const ACTION_ALL = "all"

const JOB_OPTIONS = [
  "purge_dereferenced_blobs",
  "demote_pressured_buckets",
  "promote_recently_accessed",
  "bucket_probe",
  "trim_bucket_probes",
  "trim_audit_events",
  "trim_file_events",
  "trim_maintenance_events",
] as const

const ACTION_OPTIONS = [
  "blob.purged",
  "blob.purge_failed",
  "blob.demoted",
  "blob.demotion_skipped",
  "blob.demotion_failed",
  "blob.promoted",
  "blob.promotion_skipped",
  "blob.promotion_failed",
  "bucket.probe_ok",
  "bucket.probe_failed",
  "bucket_probe.trimmed",
  "audit.trimmed",
  "file_event.trimmed",
  "maintenance_event.trimmed",
] as const

type MaintenanceEventFiltersDraft = {
  job: string
  action: string
  status: string
  batch_id: string
  bucket_id: string
  blob_id: string
  created_after: Date | undefined
  created_before: Date | undefined
}

export function MaintenanceEventsPage() {
  const [filters, setFilters] = React.useState<MaintenanceEventsQuery>({
    limit: MAINTENANCE_EVENTS_PAGE_SIZE,
    offset: 0,
  })
  const [clearDialogOpen, setClearDialogOpen] = React.useState(false)
  const [draft, setDraft] = React.useState<MaintenanceEventFiltersDraft>({
    job: JOB_ALL,
    action: ACTION_ALL,
    status: STATUS_ALL,
    batch_id: "",
    bucket_id: "",
    blob_id: "",
    created_after: undefined,
    created_before: undefined,
  })
  const maintenanceEventsQuery = useMaintenanceEvents(filters)
  const clearMaintenanceEventsMutation = useClearMaintenanceEvents()

  function applyFilters(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFilters({
      job: draft.job === JOB_ALL ? undefined : draft.job,
      action: draft.action === ACTION_ALL ? undefined : draft.action,
      status:
        draft.status === STATUS_ALL
          ? undefined
          : (draft.status as MaintenanceEventStatus),
      batch_id: draft.batch_id,
      bucket_id: draft.bucket_id,
      blob_id: draft.blob_id,
      created_after: toStartOfDayIso(draft.created_after),
      created_before: toEndOfDayIso(draft.created_before),
      limit: MAINTENANCE_EVENTS_PAGE_SIZE,
      offset: 0,
    })
  }

  function clearFilters() {
    setDraft({
      job: JOB_ALL,
      action: ACTION_ALL,
      status: STATUS_ALL,
      batch_id: "",
      bucket_id: "",
      blob_id: "",
      created_after: undefined,
      created_before: undefined,
    })
    setFilters({ limit: MAINTENANCE_EVENTS_PAGE_SIZE, offset: 0 })
  }

  function setOffset(offset: number) {
    setFilters((current) => ({ ...current, offset }))
  }

  async function clearMaintenanceEventLog() {
    try {
      await clearMaintenanceEventsMutation.mutateAsync()
      setFilters({ limit: MAINTENANCE_EVENTS_PAGE_SIZE, offset: 0 })
      setClearDialogOpen(false)
    } catch {
      // Error toast is handled by the mutation hook.
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Maintenance Events
          </h1>
          <p className="text-sm text-muted-foreground">
            Inspect cold-path storage lifecycle outcomes and retention trims.
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
                disabled={clearMaintenanceEventsMutation.isPending}
              >
                <Trash2 />
                Clear Maintenance Events
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Clear maintenance events?</AlertDialogTitle>
                <AlertDialogDescription>
                  This permanently deletes every maintenance event. New cold
                  path outcomes will continue to be recorded after the table is
                  cleared.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel
                  disabled={clearMaintenanceEventsMutation.isPending}
                >
                  Cancel
                </AlertDialogCancel>
                <AlertDialogAction
                  variant="destructive"
                  disabled={clearMaintenanceEventsMutation.isPending}
                  onClick={(event) => {
                    event.preventDefault()
                    void clearMaintenanceEventLog()
                  }}
                >
                  {clearMaintenanceEventsMutation.isPending
                    ? "Clearing..."
                    : "Clear"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <Button
            type="button"
            variant="outline"
            onClick={() => void maintenanceEventsQuery.refetch()}
            disabled={maintenanceEventsQuery.isFetching}
          >
            <RefreshCw
              className={
                maintenanceEventsQuery.isFetching ? "animate-spin" : ""
              }
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
              value={draft.job}
              onValueChange={(job) => setDraft((current) => ({ ...current, job }))}
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
            <Select
              value={draft.action}
              onValueChange={(action) =>
                setDraft((current) => ({ ...current, action }))
              }
            >
              <SelectTrigger className="h-9 w-full">
                <SelectValue placeholder="Action" />
              </SelectTrigger>
              <SelectContent className="max-h-80">
                <SelectItem value={ACTION_ALL}>Any action</SelectItem>
                {ACTION_OPTIONS.map((action) => (
                  <SelectItem key={action} value={action}>
                    {action}
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
              placeholder="Bucket ID"
              value={draft.bucket_id}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  bucket_id: event.target.value,
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
            <div className="flex gap-2 lg:col-span-2">
              <Button type="submit" className="flex-1">
                <Search />
                Apply
              </Button>
              <Button type="button" variant="outline" onClick={clearFilters}>
                <X />
                Clear
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-2 sm:flex sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Maintenance Events</CardTitle>
          {maintenanceEventsQuery.data && (
            <div className="text-xs text-muted-foreground">
              {maintenanceEventsQuery.data.total.toLocaleString()}{" "}
              {maintenanceEventsQuery.data.total === 1
                ? "maintenance event"
                : "maintenance events"}
            </div>
          )}
        </CardHeader>
        <CardContent>
          {maintenanceEventsQuery.isError ? (
            <ErrorState
              message={extractApiError(maintenanceEventsQuery.error)}
              onRetry={() => void maintenanceEventsQuery.refetch()}
            />
          ) : (
            <>
              <MaintenanceEventsTable
                maintenanceEvents={maintenanceEventsQuery.data?.items ?? []}
                isLoading={maintenanceEventsQuery.isLoading}
              />
              {maintenanceEventsQuery.data && (
                <OffsetPaginationBar
                  total={maintenanceEventsQuery.data.total}
                  limit={maintenanceEventsQuery.data.limit}
                  offset={maintenanceEventsQuery.data.offset}
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
        Could not load maintenance events
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
