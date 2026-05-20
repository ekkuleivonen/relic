import * as React from "react"
import { Upload } from "lucide-react"

import { UploadMetaFields } from "@/components/filesystem/upload-meta-fields"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { useFileUpload } from "@/hooks/use-file-upload"
import {
  UPLOAD_META_HINT,
  buildUploadMetaRecord,
  type UploadMetaRow,
} from "@/lib/upload-meta"
import { formatBytes } from "@/lib/format"

export type UploadFilesDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  folderId: string
  canSetMeta: boolean
  initialFiles?: File[]
}

export function UploadFilesDialog({
  open,
  onOpenChange,
  folderId,
  canSetMeta,
  initialFiles = [],
}: UploadFilesDialogProps) {
  const uploadFile = useFileUpload()
  const fileInputRef = React.useRef<HTMLInputElement>(null)
  const [files, setFiles] = React.useState<File[]>([])
  const [metaRows, setMetaRows] = React.useState<UploadMetaRow[]>([])

  const wasOpenRef = React.useRef(false)
  React.useEffect(() => {
    if (open && !wasOpenRef.current) {
      setFiles(initialFiles.length > 0 ? [...initialFiles] : [])
      setMetaRows([])
    }
    if (!open) {
      setFiles([])
      setMetaRows([])
    }
    wasOpenRef.current = open
  }, [open, initialFiles])

  function addFiles(next: File[]) {
    if (next.length === 0) return
    setFiles((current) => {
      const seen = new Set(current.map((file) => fileKey(file)))
      const merged = [...current]
      for (const file of next) {
        const key = fileKey(file)
        if (seen.has(key)) continue
        seen.add(key)
        merged.push(file)
      }
      return merged
    })
  }

  function removeFile(target: File) {
    setFiles((current) =>
      current.filter((file) => fileKey(file) !== fileKey(target))
    )
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (files.length === 0) return
    const meta = canSetMeta ? buildUploadMetaRecord(metaRows) : {}
    for (const file of files) {
      try {
        await uploadFile.mutateAsync({
          folder_id: folderId,
          file,
          meta: Object.keys(meta).length > 0 ? meta : undefined,
        })
      } catch {
        // hook toasts per file
      }
    }
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Upload files</DialogTitle>
          <DialogDescription>
            Choose files to upload into this folder.
            {canSetMeta
              ? " You can attach optional metadata before uploading."
              : null}
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={submit}>
          <div className="grid gap-2">
            <Label>Files</Label>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(event) => {
                addFiles(Array.from(event.currentTarget.files ?? []))
                event.currentTarget.value = ""
              }}
            />
            <Button
              type="button"
              variant="outline"
              className="w-full"
              onClick={() => fileInputRef.current?.click()}
            >
              <Upload className="size-4" />
              Choose files
            </Button>
            {files.length > 0 ? (
              <ul className="max-h-40 space-y-1 overflow-y-auto rounded-md border p-2 text-sm">
                {files.map((file) => (
                  <li
                    key={fileKey(file)}
                    className="flex items-center justify-between gap-2"
                  >
                    <span className="min-w-0 truncate font-medium">
                      {file.name}
                    </span>
                    <span className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                      {formatBytes(file.size)}
                      <button
                        type="button"
                        className="text-muted-foreground hover:text-foreground"
                        onClick={() => removeFile(file)}
                      >
                        Remove
                      </button>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-muted-foreground">
                No files selected yet.
              </p>
            )}
          </div>

          {canSetMeta ? (
            <div className="grid gap-2">
              <Label>Metadata (optional)</Label>
              <UploadMetaFields rows={metaRows} onChange={setMetaRows} />
              <p className="text-xs text-muted-foreground">{UPLOAD_META_HINT}</p>
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={uploadFile.isPending}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={uploadFile.isPending || files.length === 0}
            >
              {uploadFile.isPending
                ? "Uploading…"
                : `Upload${files.length > 0 ? ` (${files.length})` : ""}`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function fileKey(file: File) {
  return `${file.name}:${file.size}:${file.lastModified}`
}
