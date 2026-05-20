import * as React from "react"
import { CopyIcon } from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { CopyableField } from "@/components/shared/copyable-field"
import type { FilesystemEventRecord } from "@/types/filesystem-events"

type FilesystemEventDetailDrawerProps = {
  event: FilesystemEventRecord | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function FilesystemEventDetailDrawer({
  event,
  open,
  onOpenChange,
}: FilesystemEventDetailDrawerProps) {
  const payloadJson = React.useMemo(() => {
    if (!event || Object.keys(event.payload).length === 0) {
      return null
    }
    return JSON.stringify(event.payload, null, 2)
  }, [event])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg">
        {event && (
          <>
            <SheetHeader>
              <SheetTitle className="flex flex-wrap items-center gap-2 pr-8">
                <Badge variant="outline">{event.event_type}</Badge>
                <span className="font-mono text-xs text-muted-foreground">
                  seq {event.seq}
                </span>
              </SheetTitle>
              <SheetDescription>{formatDate(event.created_at)}</SheetDescription>
            </SheetHeader>

            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 pb-6">
              <DetailSection title="Identifiers">
                <div className="grid gap-3">
                  <CopyableField label="Event ID" value={event.id} />
                  <CopyableField label="Folder ID" value={event.folder_id} />
                  {event.file_id && (
                    <CopyableField label="File ID" value={event.file_id} />
                  )}
                  {event.actor_id && (
                    <CopyableField label="Actor ID" value={event.actor_id} />
                  )}
                  {event.request_id && (
                    <CopyableField label="Request ID" value={event.request_id} />
                  )}
                </div>
              </DetailSection>

              {payloadJson && (
                <DetailSection title="Payload">
                  <div className="relative">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="absolute top-2 right-2 h-7"
                      onClick={() => void copyText(payloadJson)}
                    >
                      <CopyIcon className="size-3.5" />
                      Copy
                    </Button>
                    <pre className="max-h-[min(50vh,24rem)] overflow-auto rounded-md border bg-muted/30 p-3 pr-20 font-mono text-xs">
                      {payloadJson}
                    </pre>
                  </div>
                </DetailSection>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}

function DetailSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-medium text-muted-foreground">{title}</h3>
      {children}
    </section>
  )
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value)
    toast.success("Payload copied")
  } catch {
    toast.error("Could not copy to clipboard")
  }
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "full",
    timeStyle: "long",
  }).format(new Date(value))
}
