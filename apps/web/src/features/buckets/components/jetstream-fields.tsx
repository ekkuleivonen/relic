import * as React from "react"

import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { JetStreamFormState } from "@/features/buckets/lib/jetstream-config"

type JetStreamFieldsProps = {
  idPrefix: string
  bucketId?: string
  form: JetStreamFormState
  onEnabledChange: (enabled: boolean) => void
  onFieldChange: (field: keyof Omit<JetStreamFormState, "enabled">, value: string) => void
}

export function JetStreamFields({
  idPrefix,
  bucketId,
  form,
  onEnabledChange,
  onFieldChange,
}: JetStreamFieldsProps) {
  const consumerPlaceholder = bucketId
    ? `pithosys-${bucketId}`
    : "pithosys-{bucket_id}"

  return (
    <div className="grid gap-4 rounded-lg border bg-background/60 p-3">
      <label className="flex items-start gap-3">
        <Checkbox
          checked={form.enabled}
          onCheckedChange={(checked) => onEnabledChange(checked === true)}
        />
        <span>
          <span className="block text-sm font-medium">JetStream event ingest</span>
          <span className="mt-1 block text-xs/6 text-muted-foreground">
            Pull S3 notifications from a NATS JetStream stream dedicated to this
            bucket. The worker starts and stops listeners based on this config.
          </span>
        </span>
      </label>

      {form.enabled && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="NATS URL" htmlFor={`${idPrefix}-jetstream-url`}>
            <Input
              id={`${idPrefix}-jetstream-url`}
              value={form.url}
              onChange={(event) => onFieldChange("url", event.target.value)}
              placeholder="nats://127.0.0.1:4222"
              required
            />
          </Field>
          <Field label="Stream" htmlFor={`${idPrefix}-jetstream-stream`}>
            <Input
              id={`${idPrefix}-jetstream-stream`}
              value={form.stream}
              onChange={(event) => onFieldChange("stream", event.target.value)}
              placeholder="BUCKET-MY-BUCKET"
              required
            />
          </Field>
          <Field label="Subject" htmlFor={`${idPrefix}-jetstream-subject`}>
            <Input
              id={`${idPrefix}-jetstream-subject`}
              value={form.subject}
              onChange={(event) => onFieldChange("subject", event.target.value)}
              placeholder="storage.raw.my-bucket"
              required
            />
          </Field>
          <Field label="Consumer" htmlFor={`${idPrefix}-jetstream-consumer`}>
            <Input
              id={`${idPrefix}-jetstream-consumer`}
              value={form.consumer}
              onChange={(event) =>
                onFieldChange("consumer", event.target.value)
              }
              placeholder={consumerPlaceholder}
            />
          </Field>
        </div>
      )}
    </div>
  )
}

type FieldProps = {
  children: React.ReactNode
  htmlFor: string
  label: string
}

function Field({ children, htmlFor, label }: FieldProps) {
  return (
    <div>
      <Label htmlFor={htmlFor}>{label}</Label>
      <div className="mt-1.5">{children}</div>
    </div>
  )
}
