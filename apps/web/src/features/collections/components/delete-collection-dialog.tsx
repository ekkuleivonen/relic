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
import { useDeleteCollection } from "@/features/collections/hooks/use-collections"
import type { Collection } from "@/types/collections"

type DeleteCollectionDialogProps = {
  collection: Collection
  onDeleted?: () => void
}

export function DeleteCollectionDialog({
  collection,
  onDeleted,
}: DeleteCollectionDialogProps) {
  const [open, setOpen] = React.useState(false)
  const deleteCollection = useDeleteCollection(collection.id)

  async function handleDelete() {
    try {
      await deleteCollection.mutateAsync()
      setOpen(false)
      onDeleted?.()
    } catch {
      // Error presentation is handled by the mutation's onError toast.
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="destructive" size="sm">
          <Trash2Icon />
          Delete
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete collection?</DialogTitle>
          <DialogDescription>
            This removes the saved query. Objects themselves are not changed.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-lg border bg-background/60 p-3 text-sm">
          <div className="font-medium">{collection.name}</div>
          {collection.description ? (
            <div className="mt-1 text-muted-foreground">
              {collection.description}
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen(false)}
            disabled={deleteCollection.isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() => void handleDelete()}
            disabled={deleteCollection.isPending}
          >
            {deleteCollection.isPending ? "Deleting..." : "Delete collection"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
