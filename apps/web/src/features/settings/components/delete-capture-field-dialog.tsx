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
import { useDeleteUpstreamCaptureField } from "@/features/settings/hooks/use-upstream-capture-fields"
import type { UpstreamCaptureField } from "@/types/upstream-capture"

type DeleteCaptureFieldDialogProps = {
  field: UpstreamCaptureField
}

export function DeleteCaptureFieldDialog({ field }: DeleteCaptureFieldDialogProps) {
  const [open, setOpen] = React.useState(false)
  const deleteField = useDeleteUpstreamCaptureField()

  async function handleDelete() {
    try {
      await deleteField.mutateAsync(field.id)
      setOpen(false)
    } catch {
      // Toast handled by mutation onError.
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          <Trash2Icon />
          Delete
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete capture field</DialogTitle>
          <DialogDescription>
            Remove <span className="font-mono">{field.attribute_path}</span> from
            the global capture policy. Existing object values stay until objects
            are re-imported.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen(false)}
            disabled={deleteField.isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            onClick={() => void handleDelete()}
            disabled={deleteField.isPending}
          >
            Delete field
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
