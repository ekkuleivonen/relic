import * as React from "react"
import { RefreshCw } from "lucide-react"

import { FolderCombobox } from "@/components/folder-access/folder-combobox"
import { OffsetPaginationBar } from "@/components/pagination-offset"
import { ProcessorForm } from "@/components/processors/processor-form"
import { ProcessorsTable } from "@/components/processors/processors-table"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  PROCESSORS_PAGE_SIZE,
  useCreateProcessor,
  useDeleteProcessor,
  useProcessorKinds,
  useProcessors,
  useRewindProcessor,
  useSkipStuckEvent,
  useUpdateProcessor,
} from "@/hooks/use-processors"
import { useFolderTree } from "@/hooks/use-filesystem"
import { extractApiError } from "@/lib/api"
import { flattenFolderTree, type FolderPathEntry } from "@/lib/folder-path"
import type {
  Processor,
  ProcessorCreateInput,
  ProcessorFolderScope,
} from "@/types/processors"

export function ProcessorsPage() {
  const [offset, setOffset] = React.useState(0)
  const [createOpen, setCreateOpen] = React.useState(false)
  const [scopeTarget, setScopeTarget] = React.useState<Processor | null>(null)
  const [rewindTarget, setRewindTarget] = React.useState<Processor | null>(null)
  const [skipTarget, setSkipTarget] = React.useState<Processor | null>(null)
  const [deleteTarget, setDeleteTarget] = React.useState<Processor | null>(null)

  const processorsQuery = useProcessors({
    limit: PROCESSORS_PAGE_SIZE,
    offset,
  })
  const processorKindsQuery = useProcessorKinds()
  const folderTreeQuery = useFolderTree()
  const folders = React.useMemo(
    () =>
      folderTreeQuery.data ? flattenFolderTree(folderTreeQuery.data) : [],
    [folderTreeQuery.data]
  )

  const createMutation = useCreateProcessor()
  const updateMutation = useUpdateProcessor()
  const deleteMutation = useDeleteProcessor()
  const rewindMutation = useRewindProcessor()
  const skipMutation = useSkipStuckEvent()

  const pendingProcessorId =
    updateMutation.variables?.processorId ??
    rewindMutation.variables?.processorId ??
    skipMutation.variables?.processorId ??
    deleteMutation.variables ??
    undefined

  async function handleCreate(input: ProcessorCreateInput) {
    await createMutation.mutateAsync(input)
    setCreateOpen(false)
  }

  function handleToggleEnabled(processor: Processor) {
    updateMutation.mutate({
      processorId: processor.id,
      input: { enabled: !processor.enabled },
    })
  }

  async function handleRewind(target_offset: number, reason: string) {
    if (!rewindTarget) return
    await rewindMutation.mutateAsync({
      processorId: rewindTarget.id,
      input: {
        target_offset,
        reason,
      },
    })
    setRewindTarget(null)
  }

  async function handleSkip(eventId: string, reason: string) {
    if (!skipTarget) return
    await skipMutation.mutateAsync({
      processorId: skipTarget.id,
      input: {
        event_id: eventId,
        reason,
      },
    })
    setSkipTarget(null)
  }

  async function handleDelete() {
    if (!deleteTarget) return
    await deleteMutation.mutateAsync(deleteTarget.id)
    setDeleteTarget(null)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Processors</h1>
          <p className="text-sm text-muted-foreground">
            Inspect cursor lag, pause runs, and recover from poisoned events on
            the warm <code>relic:processing</code> queue.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="button" onClick={() => setCreateOpen(true)}>
            Add Processor
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => void processorsQuery.refetch()}
            disabled={processorsQuery.isFetching}
          >
            <RefreshCw
              className={processorsQuery.isFetching ? "animate-spin" : ""}
            />
            Refresh
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="gap-2 sm:flex sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Processors</CardTitle>
          {processorsQuery.data && (
            <div className="text-xs text-muted-foreground">
              {processorsQuery.data.total.toLocaleString()}{" "}
              {processorsQuery.data.total === 1 ? "processor" : "processors"}
            </div>
          )}
        </CardHeader>
        <CardContent>
          {processorsQuery.isError ? (
            <ErrorState
              message={extractApiError(processorsQuery.error)}
              onRetry={() => void processorsQuery.refetch()}
            />
          ) : (
            <>
              <ProcessorsTable
                processors={processorsQuery.data?.items ?? []}
                folders={folders}
                isLoading={processorsQuery.isLoading}
                onToggleEnabled={handleToggleEnabled}
                onEditScopes={setScopeTarget}
                onRewind={setRewindTarget}
                onSkipStuck={setSkipTarget}
                onDelete={setDeleteTarget}
                pendingProcessorId={pendingProcessorId}
              />
              {processorsQuery.data && (
                <OffsetPaginationBar
                  total={processorsQuery.data.total}
                  limit={processorsQuery.data.limit}
                  offset={processorsQuery.data.offset}
                  onChange={setOffset}
                />
              )}
            </>
          )}
        </CardContent>
      </Card>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Processor</DialogTitle>
            <DialogDescription>
              Register a new warm-path processor. The dispatcher picks it up on
              its next tick.
            </DialogDescription>
          </DialogHeader>
          <ProcessorForm
            processorKinds={processorKindsQuery.data?.items ?? []}
            folders={folders}
            isSubmitting={createMutation.isPending}
            onCancel={() => setCreateOpen(false)}
            onSubmit={handleCreate}
          />
        </DialogContent>
      </Dialog>

      <FolderScopesDialog
        processor={scopeTarget}
        folders={folders}
        isSubmitting={updateMutation.isPending}
        onCancel={() => setScopeTarget(null)}
        onSubmit={async (folder_scopes) => {
          if (!scopeTarget) return
          await updateMutation.mutateAsync({
            processorId: scopeTarget.id,
            input: { folder_scopes },
          })
          setScopeTarget(null)
        }}
      />

      <RewindDialog
        processor={rewindTarget}
        isSubmitting={rewindMutation.isPending}
        onCancel={() => setRewindTarget(null)}
        onSubmit={handleRewind}
      />

      <SkipDialog
        processor={skipTarget}
        isSubmitting={skipMutation.isPending}
        onCancel={() => setSkipTarget(null)}
        onSubmit={handleSkip}
      />

      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete processor?</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteTarget
                ? `This permanently removes ${deleteTarget.name}. New file events will keep flowing into other processors.`
                : "Delete the selected processor."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={(event) => {
                event.preventDefault()
                void handleDelete()
              }}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
        Could not load processors
      </div>
      <p className="mt-1 text-xs text-muted-foreground">{message}</p>
      <Button className="mt-3" type="button" variant="outline" onClick={onRetry}>
        <RefreshCw className="size-3.5" />
        Retry
      </Button>
    </div>
  )
}

function FolderScopesDialog({
  processor,
  folders,
  isSubmitting,
  onCancel,
  onSubmit,
}: {
  processor: Processor | null
  folders: FolderPathEntry[]
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (folder_scopes: ProcessorFolderScope[]) => Promise<void>
}) {
  return (
    <Dialog
      open={processor !== null}
      onOpenChange={(open) => {
        if (!open) onCancel()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit folder scopes</DialogTitle>
          <DialogDescription>
            {processor
              ? `Restrict ${processor.name} to specific folders. Empty means all folders.`
              : ""}
          </DialogDescription>
        </DialogHeader>
        {processor && (
          <FolderScopesForm
            key={processor.id}
            initialScopes={processor.folder_scopes}
            folders={folders}
            isSubmitting={isSubmitting}
            onCancel={onCancel}
            onSubmit={onSubmit}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function FolderScopesForm({
  initialScopes,
  folders,
  isSubmitting,
  onCancel,
  onSubmit,
}: {
  initialScopes: ProcessorFolderScope[]
  folders: FolderPathEntry[]
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (folder_scopes: ProcessorFolderScope[]) => Promise<void>
}) {
  const [scopes, setScopes] = React.useState<ProcessorFolderScope[]>(initialScopes)
  const [folderId, setFolderId] = React.useState("")
  const [cascade, setCascade] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  function addScope() {
    if (!folderId) {
      setError("Choose a folder scope before adding it")
      return
    }
    setError(null)
    setScopes((current) => {
      const existing = current.find((scope) => scope.folder_id === folderId)
      if (existing) {
        return current.map((scope) =>
          scope.folder_id === folderId
            ? { ...scope, cascade: scope.cascade || cascade }
            : scope
        )
      }
      return [...current, { folder_id: folderId, cascade }]
    })
    setFolderId("")
    setCascade(true)
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await onSubmit(scopes)
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="space-y-2">
        <Label>Folder</Label>
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
          <FolderCombobox
            folders={folders}
            value={folderId || undefined}
            onChange={setFolderId}
            disabled={folders.length === 0}
            placeholder={
              folders.length === 0 ? "No folders available" : "Select a folder"
            }
          />
          <Button type="button" variant="outline" onClick={addScope}>
            Add Scope
          </Button>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={cascade}
            onChange={(event) => setCascade(event.target.checked)}
            className="size-4"
          />
          Include descendants
        </label>
      </div>
      <FolderScopesList
        scopes={scopes}
        folders={folders}
        onRemove={(removedFolderId) =>
          setScopes((current) =>
            current.filter((scope) => scope.folder_id !== removedFolderId)
          )
        }
      />
      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
          {error}
        </div>
      )}
      <DialogFooter>
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : "Save scopes"}
        </Button>
      </DialogFooter>
    </form>
  )
}

function FolderScopesList({
  scopes,
  folders,
  onRemove,
}: {
  scopes: ProcessorFolderScope[]
  folders: FolderPathEntry[]
  onRemove: (folderId: string) => void
}) {
  if (scopes.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
        All folders are in scope.
      </div>
    )
  }
  return (
    <div className="flex flex-wrap gap-2">
      {scopes.map((scope) => {
        const folder = folders.find((entry) => entry.id === scope.folder_id)
        return (
          <div
            key={scope.folder_id}
            className="flex items-center gap-2 rounded-md border px-2 py-1 text-xs"
          >
            <span className="font-mono">
              {folder?.path ?? scope.folder_id}
              {scope.cascade ? "/*" : ""}
            </span>
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground"
              onClick={() => onRemove(scope.folder_id)}
            >
              Remove
            </button>
          </div>
        )
      })}
    </div>
  )
}

function RewindDialog({
  processor,
  isSubmitting,
  onCancel,
  onSubmit,
}: {
  processor: Processor | null
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (target_offset: number, reason: string) => Promise<void>
}) {
  return (
    <Dialog
      open={processor !== null}
      onOpenChange={(open) => {
        if (!open) onCancel()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Rewind cursor</DialogTitle>
          <DialogDescription>
            {processor
              ? `Move ${processor.name}'s cursor. Currently at ${processor.last_committed_offset.toLocaleString()}; head at ${processor.head_offset.toLocaleString()}.`
              : ""}
          </DialogDescription>
        </DialogHeader>
        {processor && (
          <RewindForm
            key={processor.id}
            isSubmitting={isSubmitting}
            onCancel={onCancel}
            onSubmit={onSubmit}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function RewindForm({
  isSubmitting,
  onCancel,
  onSubmit,
}: {
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (target_offset: number, reason: string) => Promise<void>
}) {
  const [targetOffset, setTargetOffset] = React.useState("0")
  const [reason, setReason] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    const parsed = Number(targetOffset)
    if (!Number.isInteger(parsed) || parsed < 0) {
      setError("Target offset must be a non-negative integer")
      return
    }
    const cleanedReason = reason.trim()
    if (!cleanedReason) {
      setError("Reason is required")
      return
    }
    await onSubmit(parsed, cleanedReason)
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="space-y-2">
        <Label htmlFor="rewind-target">Target offset</Label>
        <Input
          id="rewind-target"
          value={targetOffset}
          onChange={(event) => setTargetOffset(event.target.value)}
          inputMode="numeric"
          autoFocus
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="rewind-reason">Reason</Label>
        <Textarea
          id="rewind-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={3}
          placeholder="Logged in audit_events for traceability"
        />
      </div>
      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
          {error}
        </div>
      )}
      <DialogFooter>
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Rewinding..." : "Rewind"}
        </Button>
      </DialogFooter>
    </form>
  )
}

function SkipDialog({
  processor,
  isSubmitting,
  onCancel,
  onSubmit,
}: {
  processor: Processor | null
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (eventId: string, reason: string) => Promise<void>
}) {
  return (
    <Dialog
      open={processor !== null}
      onOpenChange={(open) => {
        if (!open) onCancel()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Skip stuck event</DialogTitle>
          <DialogDescription>
            {processor
              ? `Advance ${processor.name}'s cursor past a poisoned event. The action is recorded in audit_events.`
              : ""}
          </DialogDescription>
        </DialogHeader>
        {processor && (
          <SkipForm
            key={processor.id}
            isSubmitting={isSubmitting}
            onCancel={onCancel}
            onSubmit={onSubmit}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function SkipForm({
  isSubmitting,
  onCancel,
  onSubmit,
}: {
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (eventId: string, reason: string) => Promise<void>
}) {
  const [eventId, setEventId] = React.useState("")
  const [reason, setReason] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (!eventId.trim()) {
      setError("File event ID is required")
      return
    }
    const cleanedReason = reason.trim()
    if (!cleanedReason) {
      setError("Reason is required")
      return
    }
    await onSubmit(eventId.trim(), cleanedReason)
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="space-y-2">
        <Label htmlFor="skip-event-id">File event ID</Label>
        <Input
          id="skip-event-id"
          value={eventId}
          onChange={(event) => setEventId(event.target.value)}
          autoFocus
          placeholder="00000000-0000-0000-0000-000000000000"
        />
        <p className="text-xs text-muted-foreground">
          Find the offending event ID via the File Events page.
        </p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="skip-reason">Reason</Label>
        <Textarea
          id="skip-reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          rows={3}
          placeholder="Why is this event being skipped?"
        />
      </div>
      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
          {error}
        </div>
      )}
      <DialogFooter>
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Skipping..." : "Skip"}
        </Button>
      </DialogFooter>
    </form>
  )
}
