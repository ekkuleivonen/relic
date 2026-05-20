import * as React from "react"
import { RefreshCw, X } from "lucide-react"

import { FilesystemEventDetailDrawer } from "@/components/filesystem-events/filesystem-event-detail-drawer"
import { FilesystemEventTypeCombobox } from "@/components/filesystem-events/filesystem-event-type-combobox"
import { FilesystemEventsTable } from "@/components/filesystem-events/filesystem-events-table"
import { FilterFieldLabel } from "@/components/filters/filter-field-label"
import { FolderCombobox } from "@/components/folder-access/folder-combobox"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  FILESYSTEM_EVENTS_PAGE_SIZE,
  useFilesystemEvents,
} from "@/hooks/use-filesystem-events"
import { useDebouncedValue } from "@/hooks/use-debounced-value"
import { useFolderTree } from "@/hooks/use-filesystem"
import { extractApiError } from "@/lib/api"
import { flattenFolderTree } from "@/lib/folder-path"
import type {
  FilesystemEventRecord,
  FilesystemEventsQuery,
} from "@/types/filesystem-events"

const AFTER_SEQ_DEBOUNCE_MS = 400

export function FilesystemEventsPage() {
  const [afterInput, setAfterInput] = React.useState("0")
  const [folderId, setFolderId] = React.useState<string | undefined>()
  const [eventType, setEventType] = React.useState<string | undefined>()
  const [recursive, setRecursive] = React.useState(false)
  const [selectedEvent, setSelectedEvent] =
    React.useState<FilesystemEventRecord | null>(null)

  const debouncedAfterInput = useDebouncedValue(afterInput, AFTER_SEQ_DEBOUNCE_MS)

  const filters = React.useMemo<FilesystemEventsQuery>(
    () => ({
      after: parseAfterSeq(debouncedAfterInput),
      folder_id: folderId,
      recursive,
      types: eventType ? [eventType] : undefined,
      limit: FILESYSTEM_EVENTS_PAGE_SIZE,
    }),
    [debouncedAfterInput, folderId, eventType, recursive]
  )

  const treeQuery = useFolderTree()
  const folderOptions = React.useMemo(
    () => (treeQuery.data ? flattenFolderTree(treeQuery.data) : []),
    [treeQuery.data]
  )

  const eventsQuery = useFilesystemEvents(filters)
  const events = [...(eventsQuery.data?.items ?? [])].reverse()

  function resetFilters() {
    setAfterInput("0")
    setFolderId(undefined)
    setEventType(undefined)
    setRecursive(false)
    setSelectedEvent(null)
  }

  function loadNewer() {
    const cursor = eventsQuery.data?.cursor
    if (cursor == null) {
      return
    }
    setAfterInput(String(cursor))
  }

  const hasActiveFilters =
    afterInput !== "0" ||
    folderId !== undefined ||
    eventType !== undefined ||
    recursive

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Filesystem Events
          </h1>
          <p className="text-sm text-muted-foreground">
            Integrator subscription log — file and folder lifecycle changes.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void eventsQuery.refetch()}
          disabled={eventsQuery.isFetching}
        >
          <RefreshCw
            className={eventsQuery.isFetching ? "animate-spin" : ""}
          />
          Refresh
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="grid gap-2">
                <FilterFieldLabel
                  htmlFor="after-seq"
                  label="After seq"
                  tooltip="Return events with seq greater than this value. Use 0 from a cold start, or the cursor from a previous response to poll for newer events."
                />
                <Input
                  id="after-seq"
                  className="h-9"
                  value={afterInput}
                  onChange={(event) => setAfterInput(event.target.value)}
                  placeholder="0"
                />
              </div>

              <div className="grid gap-2">
                <FilterFieldLabel
                  label="Folder"
                  tooltip="Scope to events anchored on this folder (the ACL visibility parent). Leave empty to include all folders you can see."
                />
                <FolderCombobox
                  folders={folderOptions}
                  value={folderId}
                  onChange={setFolderId}
                  disabled={treeQuery.isLoading}
                  placeholder="Any folder"
                  allowClear
                  clearLabel="Any folder"
                />
              </div>

              <div className="grid gap-2">
                <FilterFieldLabel
                  label="Event type"
                  tooltip="Filter by subscription event type, such as file.created or folder.deleted."
                />
                <FilesystemEventTypeCombobox
                  value={eventType}
                  onChange={setEventType}
                />
              </div>

              <div className="grid gap-2">
                <FilterFieldLabel
                  htmlFor="recursive-scope"
                  label="Recursive scope"
                  tooltip="When a folder is selected, also include events from its subfolders."
                />
                <div className="flex h-9 items-center gap-2">
                  <Checkbox
                    id="recursive-scope"
                    checked={recursive}
                    onCheckedChange={(checked) =>
                      setRecursive(checked === true)
                    }
                  />
                  <Label
                    htmlFor="recursive-scope"
                    className="cursor-pointer font-normal text-muted-foreground"
                  >
                    Include subfolders
                  </Label>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              {hasActiveFilters && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={resetFilters}
                >
                  <X className="size-4" />
                  Reset
                </Button>
              )}
              {eventsQuery.data?.has_more && (
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={loadNewer}
                >
                  Load newer (after {eventsQuery.data.cursor})
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <FilesystemEventsTable
        events={events}
        isLoading={eventsQuery.isLoading}
        selectedEventId={selectedEvent?.id}
        onSelectEvent={setSelectedEvent}
      />

      {eventsQuery.isError && (
        <div className="rounded-md border border-destructive/20 bg-destructive/5 p-4 text-sm">
          <div className="font-medium text-destructive">
            Could not load filesystem events
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {extractApiError(eventsQuery.error)}
          </p>
        </div>
      )}

      <FilesystemEventDetailDrawer
        event={selectedEvent}
        open={selectedEvent !== null}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedEvent(null)
          }
        }}
      />

      {eventsQuery.data && (
        <p className="text-xs text-muted-foreground">
          Showing {eventsQuery.data.items.length} events
          {eventsQuery.data.oldest_seq != null
            ? ` · oldest retained seq ${eventsQuery.data.oldest_seq}`
            : ""}
          {eventsQuery.data.has_more ? " · more available" : ""}
        </p>
      )}
    </div>
  )
}

function parseAfterSeq(value: string) {
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0
}
