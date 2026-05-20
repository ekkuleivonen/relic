import * as React from "react"

import { StorageBackendForm } from "@/components/storage-backends/storage-backend-form"
import { StorageBackendsTable } from "@/components/storage-backends/storage-backends-table"
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
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useBlobGc } from "@/hooks/use-blobs"
import {
  useCreateStorageBackend,
  useDeleteStorageBackend,
  useDrainStorageBackend,
  useProbeStorageBackend,
  useStorageBackends,
  useUpdateStorageBackend,
} from "@/hooks/use-storage-backends"
import type {
  StorageBackend,
  StorageBackendCreateInput,
  StorageBackendUpdateInput,
} from "@/types/storage-backends"

export function StorageBackendsPage() {
  const storageBackendsQuery = useStorageBackends()
  const createStorageBackend = useCreateStorageBackend()
  const updateStorageBackend = useUpdateStorageBackend()
  const deleteStorageBackend = useDeleteStorageBackend()
  const probeStorageBackend = useProbeStorageBackend()
  const drainStorageBackend = useDrainStorageBackend()
  const blobGc = useBlobGc()

  const [isCreateOpen, setIsCreateOpen] = React.useState(false)
  const [editingStorageBackend, setEditingStorageBackend] =
    React.useState<StorageBackend | null>(null)
  const [deletingStorageBackend, setDeletingStorageBackend] =
    React.useState<StorageBackend | null>(null)
  const [drainingStorageBackend, setDrainingStorageBackend] =
    React.useState<StorageBackend | null>(null)
  const [gcConfirmOpen, setGcConfirmOpen] = React.useState(false)

  async function handleCreate(values: StorageBackendCreateInput) {
    const storageBackend = await createStorageBackend.mutateAsync(values)
    setIsCreateOpen(false)
    await probeStorageBackend.mutateAsync(storageBackend.id)
  }

  async function handleUpdate(values: StorageBackendCreateInput) {
    if (!editingStorageBackend) {
      return
    }

    const input: StorageBackendUpdateInput = {
      name: values.name,
      endpoint: values.endpoint,
      namespace: values.namespace,
      max_size_bytes: values.max_size_bytes,
    }

    if (editingStorageBackend.kind === "s3") {
      input.region = values.region
      if (values.key_id?.trim()) {
        input.key_id = values.key_id.trim()
      }
      if (values.secret_access_key?.trim()) {
        input.secret_access_key = values.secret_access_key.trim()
      }
    }

    await updateStorageBackend.mutateAsync({
      storageBackendId: editingStorageBackend.id,
      input,
    })
    setEditingStorageBackend(null)
  }

  async function handleDelete() {
    if (!deletingStorageBackend) {
      return
    }

    await deleteStorageBackend.mutateAsync(deletingStorageBackend.id)
    setDeletingStorageBackend(null)
  }

  async function handleDrain() {
    if (!drainingStorageBackend) {
      return
    }

    await drainStorageBackend.mutateAsync(drainingStorageBackend.id)
    setDrainingStorageBackend(null)
  }

  async function handleGc() {
    await blobGc.mutateAsync()
    setGcConfirmOpen(false)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Storage Backends
          </h1>
          <p className="text-sm text-muted-foreground">
            Register and manage S3-compatible, filesystem, and future cloud
            storage backends.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => setGcConfirmOpen(true)}
            disabled={blobGc.isPending}
          >
            {blobGc.isPending ? "Running GC..." : "Run Blob GC"}
          </Button>
          <Button type="button" onClick={() => setIsCreateOpen(true)}>
            Add Storage Backend
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Registered Backends</CardTitle>
        </CardHeader>
        <CardContent>
          <StorageBackendsTable
            storageBackends={storageBackendsQuery.data ?? []}
            isLoading={storageBackendsQuery.isLoading}
            probingId={probeStorageBackend.variables}
            drainingId={drainStorageBackend.variables}
            onEdit={setEditingStorageBackend}
            onDelete={setDeletingStorageBackend}
            onProbe={(storageBackend) =>
              probeStorageBackend.mutate(storageBackend.id)
            }
            onDrain={setDrainingStorageBackend}
          />
        </CardContent>
      </Card>

      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Storage Backend</DialogTitle>
            <DialogDescription>
              Register a remote S3-compatible namespace or a local filesystem
              directory for Relic to place blobs.
            </DialogDescription>
          </DialogHeader>
          <StorageBackendForm
            submitLabel="Create Backend"
            isSubmitting={createStorageBackend.isPending}
            onCancel={() => setIsCreateOpen(false)}
            onSubmit={handleCreate}
          />
        </DialogContent>
      </Dialog>

      <Dialog
        open={editingStorageBackend !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditingStorageBackend(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Storage Backend</DialogTitle>
            <DialogDescription>
              Update connection details, capacity, or credentials for this
              backend.
            </DialogDescription>
          </DialogHeader>
          {editingStorageBackend && (
            <StorageBackendForm
              key={editingStorageBackend.id}
              storageBackend={editingStorageBackend}
              submitLabel="Save Changes"
              isSubmitting={updateStorageBackend.isPending}
              onCancel={() => setEditingStorageBackend(null)}
              onSubmit={handleUpdate}
            />
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={deletingStorageBackend !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeletingStorageBackend(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete storage backend?</AlertDialogTitle>
            <AlertDialogDescription>
              {deletingStorageBackend
                ? `This will remove ${deletingStorageBackend.name}. The backend API will refuse this if blobs still reference it.`
                : "This will remove the selected storage backend."}
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
              disabled={deleteStorageBackend.isPending}
            >
              {deleteStorageBackend.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog
        open={drainingStorageBackend !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDrainingStorageBackend(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Drain storage backend?</AlertDialogTitle>
            <AlertDialogDescription>
              {drainingStorageBackend
                ? `This migrates all blobs out of ${drainingStorageBackend.name} into colder backends with capacity.`
                : "This migrates all blobs out of the selected storage backend."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault()
                void handleDrain()
              }}
              disabled={drainStorageBackend.isPending}
            >
              {drainStorageBackend.isPending ? "Draining..." : "Drain"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={gcConfirmOpen} onOpenChange={setGcConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Run blob garbage collection?</AlertDialogTitle>
            <AlertDialogDescription>
              Purges dereferenced blobs (refcount zero) from storage and the
              database. This runs one maintenance batch immediately.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault()
                void handleGc()
              }}
              disabled={blobGc.isPending}
            >
              {blobGc.isPending ? "Running..." : "Run GC"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
