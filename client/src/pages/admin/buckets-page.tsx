import * as React from "react"

import { BucketForm } from "@/components/buckets/bucket-form"
import { BucketsTable } from "@/components/buckets/buckets-table"
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
import {
  useBuckets,
  useCreateBucket,
  useDeleteBucket,
  useProbeBucket,
  useUpdateBucket,
} from "@/hooks/use-buckets"
import type { Bucket, BucketCreateInput } from "@/types/buckets"

export function BucketsPage() {
  const bucketsQuery = useBuckets()
  const createBucket = useCreateBucket()
  const updateBucket = useUpdateBucket()
  const deleteBucket = useDeleteBucket()
  const probeBucket = useProbeBucket()

  const [isCreateOpen, setIsCreateOpen] = React.useState(false)
  const [editingBucket, setEditingBucket] = React.useState<Bucket | null>(null)
  const [deletingBucket, setDeletingBucket] = React.useState<Bucket | null>(null)

  async function handleCreate(values: BucketCreateInput) {
    const bucket = await createBucket.mutateAsync(values)
    setIsCreateOpen(false)
    await probeBucket.mutateAsync(bucket.id)
  }

  async function handleUpdate(values: BucketCreateInput) {
    if (!editingBucket) {
      return
    }

    await updateBucket.mutateAsync({
      bucketId: editingBucket.id,
      input: {
        name: values.name,
        endpoint: values.endpoint,
        region: values.region,
        bucket: values.bucket,
        key_id: values.key_id,
        secret_access_key: values.secret_access_key,
        tier: values.tier,
        max_size_bytes: values.max_size_bytes,
      },
    })
    setEditingBucket(null)
  }

  async function handleDelete() {
    if (!deletingBucket) {
      return
    }

    await deleteBucket.mutateAsync(deletingBucket.id)
    setDeletingBucket(null)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Buckets</h1>
          <p className="text-sm text-muted-foreground">
            Register and manage S3-compatible remote buckets.
          </p>
        </div>
        <Button type="button" onClick={() => setIsCreateOpen(true)}>
          Add Bucket
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Bucket Backends</CardTitle>
        </CardHeader>
        <CardContent>
          <BucketsTable
            buckets={bucketsQuery.data ?? []}
            isLoading={bucketsQuery.isLoading}
            probingId={probeBucket.variables}
            onEdit={setEditingBucket}
            onDelete={setDeletingBucket}
            onProbe={(bucket) => probeBucket.mutate(bucket.id)}
          />
        </CardContent>
      </Card>

      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Bucket</DialogTitle>
            <DialogDescription>
              Register an S3-compatible remote bucket for Relic to place blobs.
            </DialogDescription>
          </DialogHeader>
          <BucketForm
            submitLabel="Create Bucket"
            isSubmitting={createBucket.isPending}
            onCancel={() => setIsCreateOpen(false)}
            onSubmit={handleCreate}
          />
        </DialogContent>
      </Dialog>

      <Dialog
        open={editingBucket !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditingBucket(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Bucket</DialogTitle>
            <DialogDescription>
              Update connection details, credentials, tier, or capacity for this
              backend.
            </DialogDescription>
          </DialogHeader>
          {editingBucket && (
            <BucketForm
              key={editingBucket.id}
              bucketRecord={editingBucket}
              submitLabel="Save Changes"
              isSubmitting={updateBucket.isPending}
              onCancel={() => setEditingBucket(null)}
              onSubmit={handleUpdate}
            />
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={deletingBucket !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeletingBucket(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete bucket backend?</AlertDialogTitle>
            <AlertDialogDescription>
              {deletingBucket
                ? `This will remove ${deletingBucket.name}. The backend API will refuse this if blobs still reference it.`
                : "This will remove the selected bucket backend."}
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
              disabled={deleteBucket.isPending}
            >
              {deleteBucket.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
