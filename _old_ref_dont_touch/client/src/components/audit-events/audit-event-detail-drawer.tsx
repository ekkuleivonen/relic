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
import type { AuditEventRecord } from "@/types/audit-events"

type AuditEventDetailDrawerProps = {
  event: AuditEventRecord | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function AuditEventDetailDrawer({
  event,
  open,
  onOpenChange,
}: AuditEventDetailDrawerProps) {
  const metadataJson = React.useMemo(() => {
    if (!event || Object.keys(event.metadata).length === 0) {
      return null
    }
    return JSON.stringify(event.metadata, null, 2)
  }, [event])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg">
        {event && (
          <>
            <SheetHeader>
              <SheetTitle className="flex flex-wrap items-center gap-2 pr-8">
                <span className="font-medium">{event.operation}</span>
                <StatusBadge status={event.status} />
              </SheetTitle>
              <SheetDescription>{formatDate(event.created_at)}</SheetDescription>
            </SheetHeader>

            <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 pb-6">
              <DetailSection title="Summary">
                <dl className="grid gap-2 text-xs">
                  <DetailRow label="Job" value={event.job} />
                  <DetailRow
                    label="Duration"
                    value={
                      event.duration_ms == null
                        ? null
                        : `${event.duration_ms} ms`
                    }
                  />
                  <DetailRow
                    label="Actor"
                    value={
                      event.actor
                        ? `${event.actor.name} · ${event.actor.email}`
                        : "System"
                    }
                  />
                </dl>
              </DetailSection>

              <DetailSection title="Identifiers">
                <div className="grid gap-3">
                  <CopyableField label="Event ID" value={event.id} />
                  {event.actor_id && (
                    <CopyableField label="Actor ID" value={event.actor_id} />
                  )}
                  {event.request_id && (
                    <CopyableField label="Request ID" value={event.request_id} />
                  )}
                  {event.batch_id && (
                    <CopyableField label="Batch ID" value={event.batch_id} />
                  )}
                  {event.storage_backend_id && (
                    <CopyableField
                      label="Storage Backend ID"
                      value={event.storage_backend_id}
                    />
                  )}
                  {event.blob_id && (
                    <CopyableField label="Blob ID" value={event.blob_id} />
                  )}
                </div>
              </DetailSection>

              {metadataJson && (
                <DetailSection title="Metadata">
                  <div className="relative">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="absolute top-2 right-2 h-7"
                      onClick={() => void copyText(metadataJson)}
                    >
                      <CopyIcon className="size-3.5" />
                      Copy
                    </Button>
                    <pre className="max-h-[min(50vh,24rem)] overflow-auto rounded-md border bg-muted/30 p-3 pr-20 font-mono text-xs">
                      {metadataJson}
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

function DetailRow({
  label,
  value,
}: {
  label: string
  value: string | null | undefined
}) {
  if (!value) {
    return null
  }

  return (
    <div className="flex gap-2">
      <dt className="w-20 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{value}</dd>
    </div>
  )
}

function StatusBadge({ status }: { status: AuditEventRecord["status"] }) {
  if (status === "failed") {
    return <Badge variant="destructive">{status}</Badge>
  }

  if (status === "skipped") {
    return <Badge variant="outline">{status}</Badge>
  }

  return <Badge variant="secondary">{status}</Badge>
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value)
    toast.success("Metadata copied")
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
