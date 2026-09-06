import * as React from "react"
import { PencilIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useUpdateBucket } from "@/features/buckets/hooks/use-buckets"
import { JetStreamFields } from "@/features/buckets/components/jetstream-fields"
import {
  jetstreamFormFromUpstreamConfig,
  upstreamConfigWithJetstream,
} from "@/features/buckets/lib/jetstream-config"
import type { Bucket, UpdateBucketInput } from "@/types/buckets"

type EditBucketDialogProps = {
  bucket: Bucket
  triggerLabel?: string
}

export function EditBucketDialog({
  bucket,
  triggerLabel = "Edit",
}: EditBucketDialogProps) {
  const [open, setOpen] = React.useState(false)
  const [form, setForm] = React.useState(() => formStateFromBucket(bucket))
  const updateBucket = useUpdateBucket(bucket.id)

  function handleOpenChange(nextOpen: boolean) {
    if (nextOpen) {
      setForm(formStateFromBucket(bucket))
    }
    setOpen(nextOpen)
  }

  function updateField(name: keyof typeof form, value: string | boolean) {
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const input: UpdateBucketInput = {
      name: form.name,
      endpoint_url: form.endpointUrl,
      region: form.region,
      prefix: form.prefix,
      upstream_config: upstreamConfigWithJetstream(
        {
          ...bucket.upstream_config,
          s3: {
            ...(isRecord(bucket.upstream_config.s3)
              ? bucket.upstream_config.s3
              : {}),
            force_path_style: form.forcePathStyle,
            signing_region: form.region,
          },
        },
        {
          enabled: form.jetstreamEnabled,
          url: form.jetstreamUrl,
          stream: form.jetstreamStream,
          subject: form.jetstreamSubject,
          consumer: form.jetstreamConsumer,
        },
      ),
    }
    if (form.rotateCredentials) {
      input.credentials = {
        access_key_id: form.accessKeyId,
        secret_access_key: form.secretAccessKey,
        ...(form.sessionToken
          ? {
              session_token: form.sessionToken,
            }
          : {}),
      }
    }

    try {
      await updateBucket.mutateAsync(input)
      setOpen(false)
    } catch {
      // Error presentation is handled by the mutation's onError toast.
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <PencilIcon />
          {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <form onSubmit={handleSubmit} className="grid gap-5">
          <DialogHeader>
            <DialogTitle>Edit bucket</DialogTitle>
            <DialogDescription>
              Update Pithosys's connection metadata for this bucket. Stored
              credentials are left unchanged unless you rotate them below.
              Scheduled scan settings are configured globally under Settings →
              Jobs.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Display name" htmlFor={`edit-name-${bucket.id}`}>
              <Input
                id={`edit-name-${bucket.id}`}
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                required
              />
            </Field>
            <Field label="Bucket name" htmlFor={`edit-bucket-name-${bucket.id}`}>
              <Input
                id={`edit-bucket-name-${bucket.id}`}
                value={bucket.bucket_name}
                disabled
              />
            </Field>
            <Field label="Endpoint URL" htmlFor={`edit-endpoint-${bucket.id}`}>
              <Input
                id={`edit-endpoint-${bucket.id}`}
                value={form.endpointUrl}
                onChange={(event) =>
                  updateField("endpointUrl", event.target.value)
                }
                required
              />
            </Field>
            <Field label="Region" htmlFor={`edit-region-${bucket.id}`}>
              <Input
                id={`edit-region-${bucket.id}`}
                value={form.region}
                onChange={(event) => updateField("region", event.target.value)}
                required
              />
            </Field>
            <Field label="Prefix" htmlFor={`edit-prefix-${bucket.id}`}>
              <Input
                id={`edit-prefix-${bucket.id}`}
                value={form.prefix}
                onChange={(event) => updateField("prefix", event.target.value)}
                placeholder="All objects"
              />
            </Field>
          </div>

          <label className="flex items-start gap-3 rounded-lg border bg-background/60 p-3">
            <Checkbox
              checked={form.forcePathStyle}
              onCheckedChange={(checked) =>
                updateField("forcePathStyle", checked === true)
              }
            />
            <span>
              <span className="block text-sm font-medium">
                Force path-style addressing
              </span>
              <span className="mt-1 block text-xs/6 text-muted-foreground">
                Useful for MinIO and many S3-compatible local or self-hosted
                endpoints.
              </span>
            </span>
          </label>

          <JetStreamFields
            idPrefix={`edit-${bucket.id}`}
            bucketId={bucket.id}
            form={{
              enabled: form.jetstreamEnabled,
              url: form.jetstreamUrl,
              stream: form.jetstreamStream,
              subject: form.jetstreamSubject,
              consumer: form.jetstreamConsumer,
            }}
            onEnabledChange={(enabled) =>
              updateField("jetstreamEnabled", enabled)
            }
            onFieldChange={(field, value) => {
              switch (field) {
                case "url":
                  updateField("jetstreamUrl", value)
                  break
                case "stream":
                  updateField("jetstreamStream", value)
                  break
                case "subject":
                  updateField("jetstreamSubject", value)
                  break
                case "consumer":
                  updateField("jetstreamConsumer", value)
                  break
              }
            }}
          />

          <div className="grid gap-4 rounded-lg border bg-background/60 p-3 sm:grid-cols-2">
            <label className="flex items-start gap-3 sm:col-span-2">
              <Checkbox
                checked={form.rotateCredentials}
                onCheckedChange={(checked) =>
                  updateField("rotateCredentials", checked === true)
                }
              />
              <span>
                <span className="block text-sm font-medium">
                  Rotate credentials
                </span>
                <span className="mt-1 block text-xs/6 text-muted-foreground">
                  Leave this off to keep existing encrypted credentials. Turn it
                  on to replace them with new values.
                </span>
              </span>
            </label>

            {form.rotateCredentials && (
              <>
                <Field
                  label="Access key ID"
                  htmlFor={`edit-access-key-id-${bucket.id}`}
                >
                  <Input
                    id={`edit-access-key-id-${bucket.id}`}
                    value={form.accessKeyId}
                    onChange={(event) =>
                      updateField("accessKeyId", event.target.value)
                    }
                    autoComplete="off"
                    required
                  />
                </Field>
                <Field
                  label="Secret access key"
                  htmlFor={`edit-secret-access-key-${bucket.id}`}
                >
                  <Input
                    id={`edit-secret-access-key-${bucket.id}`}
                    type="password"
                    value={form.secretAccessKey}
                    onChange={(event) =>
                      updateField("secretAccessKey", event.target.value)
                    }
                    autoComplete="off"
                    required
                  />
                </Field>
                <Field
                  label="Session token"
                  htmlFor={`edit-session-token-${bucket.id}`}
                >
                  <Input
                    id={`edit-session-token-${bucket.id}`}
                    type="password"
                    value={form.sessionToken}
                    onChange={(event) =>
                      updateField("sessionToken", event.target.value)
                    }
                    autoComplete="off"
                    placeholder="Optional"
                  />
                </Field>
              </>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={updateBucket.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={updateBucket.isPending}>
              {updateBucket.isPending ? "Saving..." : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function formStateFromBucket(bucket: Bucket) {
  const s3Config = isRecord(bucket.upstream_config.s3)
    ? bucket.upstream_config.s3
    : {}
  const jetstream = jetstreamFormFromUpstreamConfig(bucket.upstream_config)

  return {
    name: bucket.name,
    endpointUrl: bucket.endpoint_url,
    region: bucket.region,
    prefix: bucket.prefix,
    forcePathStyle: s3Config.force_path_style === true,
    jetstreamEnabled: jetstream.enabled,
    jetstreamUrl: jetstream.url,
    jetstreamStream: jetstream.stream,
    jetstreamSubject: jetstream.subject,
    jetstreamConsumer: jetstream.consumer,
    rotateCredentials: false,
    accessKeyId: "",
    secretAccessKey: "",
    sessionToken: "",
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
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
