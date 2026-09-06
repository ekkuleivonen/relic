import * as React from "react"
import { Trash2Icon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { useDeleteBucket } from "@/features/buckets/hooks/use-buckets"
import type { Bucket } from "@/types/buckets"

type DeleteBucketDialogProps = {
  bucket: Bucket
  onDeleted?: () => void
  triggerLabel?: string
}

export function DeleteBucketDialog({
  bucket,
  onDeleted,
  triggerLabel = "Delete",
}: DeleteBucketDialogProps) {
  const [open, setOpen] = React.useState(false)
  const deleteBucket = useDeleteBucket(bucket.id)

  async function handleDelete() {
    try {
      await deleteBucket.mutateAsync()
      setOpen(false)
      onDeleted?.()
    } catch {
      // Error presentation is handled by the mutation's onError toast.
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="destructive">
          <Trash2Icon />
          {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete bucket?</DialogTitle>
          <DialogDescription>
            This removes the Pithosys bucket connection and all catalog objects
            synced under it. It does not delete anything from the upstream
            bucket.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-lg border bg-background/60 p-3 text-sm">
          <div className="font-medium">{bucket.name}</div>
          <div className="mt-1 break-words text-muted-foreground">
            {bucket.bucket_name}
            {bucket.prefix ? `/${bucket.prefix}` : ""}
          </div>
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen(false)}
            disabled={deleteBucket.isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() => void handleDelete()}
            disabled={deleteBucket.isPending}
          >
            {deleteBucket.isPending ? "Deleting..." : "Delete bucket"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
