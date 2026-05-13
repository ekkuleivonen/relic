import * as React from "react"
import { CalendarIcon, RefreshCw, Search, Trash2, X } from "lucide-react"

import { FileEventsTable } from "@/components/file-events/file-events-table"
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
  FILE_EVENTS_PAGE_SIZE,
  useClearFileEvents,
  useFileEvents,
} from "@/hooks/use-file-events"
import { extractApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { FileEventsQuery, FileEventStatus } from "@/types/file-events"

const STATUS_ALL = "all"
const EVENT_TYPE_ALL = "all"

const EVENT_TYPE_OPTIONS = [
  "file.created",
  "file.updated",
  "file.metadata.updated",
  "file.moved",
  "file.copied",
  "file.deleted",
  "folder.created",
  "folder.updated",
  "folder.moved",
  "folder.deleted",
  "processor.meta_extract.completed",
  "processor.meta_extract.failed",
] as const

type FileEventFiltersDraft = {
  event_type: string
  status: string
  actor_user_id: string
  request_id: string
  file_id: string
  folder_id: string
  created_after: Date | undefined
  created_before: Date | undefined
}

export function FileEventsPage() {
  const [filters, setFilters] = React.useState<FileEventsQuery>({
    limit: FILE_EVENTS_PAGE_SIZE,
    offset: 0,
  })
  const [clearDialogOpen, setClearDialogOpen] = React.useState(false)
  const [draft, setDraft] = React.useState<FileEventFiltersDraft>({
    event_type: EVENT_TYPE_ALL,
    status: STATUS_ALL,
    actor_user_id: "",
    request_id: "",
    file_id: "",
    folder_id: "",
    created_after: undefined,
    created_before: undefined,
  })
  const fileEventsQuery = useFileEvents(filters)
  const clearFileEventsMutation = useClearFileEvents()

  function applyFilters(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setFilters({
      event_type:
        draft.event_type === EVENT_TYPE_ALL ? undefined : draft.event_type,
      status:
        draft.status === STATUS_ALL
          ? undefined
          : (draft.status as FileEventStatus),
      actor_user_id: draft.actor_user_id,
      request_id: draft.request_id,
      file_id: draft.file_id,
      folder_id: draft.folder_id,
      created_after: toStartOfDayIso(draft.created_after),
      created_before: toEndOfDayIso(draft.created_before),
      limit: FILE_EVENTS_PAGE_SIZE,
      offset: 0,
    })
  }

  function clearFilters() {
    setDraft({
      event_type: EVENT_TYPE_ALL,
      status: STATUS_ALL,
      actor_user_id: "",
      request_id: "",
      file_id: "",
      folder_id: "",
      created_after: undefined,
      created_before: undefined,
    })
    setFilters({ limit: FILE_EVENTS_PAGE_SIZE, offset: 0 })
  }

  function setOffset(offset: number) {
    setFilters((current) => ({ ...current, offset }))
  }

  async function clearFileEventLog() {
    try {
      await clearFileEventsMutation.mutateAsync()
      setFilters({ limit: FILE_EVENTS_PAGE_SIZE, offset: 0 })
      setClearDialogOpen(false)
    } catch {
      // Error toast is handled by the mutation hook.
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">File Events</h1>
          <p className="text-sm text-muted-foreground">
            Explore durable content activity and processor outcome events.
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
                disabled={clearFileEventsMutation.isPending}
              >
                <Trash2 />
                Clear File Events
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Clear file events?</AlertDialogTitle>
                <AlertDialogDescription>
                  This permanently deletes every file event. New file events
                  will continue to be recorded after the table is cleared.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel
                  disabled={clearFileEventsMutation.isPending}
                >
                  Cancel
                </AlertDialogCancel>
                <AlertDialogAction
                  variant="destructive"
                  disabled={clearFileEventsMutation.isPending}
                  onClick={(event) => {
                    event.preventDefault()
                    void clearFileEventLog()
                  }}
                >
                  {clearFileEventsMutation.isPending ? "Clearing..." : "Clear"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
          <Button
            type="button"
            variant="outline"
            onClick={() => void fileEventsQuery.refetch()}
            disabled={fileEventsQuery.isFetching}
          >
            <RefreshCw
              className={fileEventsQuery.isFetching ? "animate-spin" : ""}
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
              value={draft.event_type}
              onValueChange={(event_type) =>
                setDraft((current) => ({ ...current, event_type }))
              }
            >
              <SelectTrigger className="h-9 w-full">
                <SelectValue placeholder="Event type" />
              </SelectTrigger>
              <SelectContent className="max-h-80">
                <SelectItem value={EVENT_TYPE_ALL}>Any event type</SelectItem>
                {EVENT_TYPE_OPTIONS.map((eventType) => (
                  <SelectItem key={eventType} value={eventType}>
                    {eventType}
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
            <Input
              placeholder="File ID"
              value={draft.file_id}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  file_id: event.target.value,
                }))
              }
            />
            <Input
              placeholder="Folder ID"
              value={draft.folder_id}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  folder_id: event.target.value,
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
          <CardTitle>File Events</CardTitle>
          {fileEventsQuery.data && (
            <div className="text-xs text-muted-foreground">
              {fileEventsQuery.data.total.toLocaleString()}{" "}
              {fileEventsQuery.data.total === 1 ? "file event" : "file events"}
            </div>
          )}
        </CardHeader>
        <CardContent>
          {fileEventsQuery.isError ? (
            <ErrorState
              message={extractApiError(fileEventsQuery.error)}
              onRetry={() => void fileEventsQuery.refetch()}
            />
          ) : (
            <>
              <FileEventsTable
                fileEvents={fileEventsQuery.data?.items ?? []}
                isLoading={fileEventsQuery.isLoading}
              />
              {fileEventsQuery.data && (
                <OffsetPaginationBar
                  total={fileEventsQuery.data.total}
                  limit={fileEventsQuery.data.limit}
                  offset={fileEventsQuery.data.offset}
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
        Could not load file events
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
