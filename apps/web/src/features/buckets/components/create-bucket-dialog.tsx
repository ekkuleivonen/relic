import * as React from "react"
import { PlusIcon } from "lucide-react"

import { Checkbox } from "@/components/ui/checkbox"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useCreateBucket } from "@/features/buckets/hooks/use-buckets"
import { JetStreamFields } from "@/features/buckets/components/jetstream-fields"
import { upstreamConfigWithJetstream } from "@/features/buckets/lib/jetstream-config"
import type { CreateBucketInput } from "@/types/buckets"

const initialFormState = {
  name: "",
  endpointUrl: "https://s3.amazonaws.com",
  region: "us-east-1",
  bucketName: "",
  prefix: "",
  accessKeyId: "",
  secretAccessKey: "",
  sessionToken: "",
  forcePathStyle: false,
  jetstreamEnabled: false,
  jetstreamUrl: "",
  jetstreamStream: "",
  jetstreamSubject: "",
  jetstreamConsumer: "",
}

type CreateBucketDialogProps = {
  triggerLabel?: string
}

export function CreateBucketDialog({
  triggerLabel = "Add bucket",
}: CreateBucketDialogProps) {
  const [open, setOpen] = React.useState(false)
  const [form, setForm] = React.useState(initialFormState)
  const createBucket = useCreateBucket()

  function updateField(name: keyof typeof form, value: string | boolean) {
    setForm((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const input: CreateBucketInput = {
      name: form.name,
      upstream: "s3",
      endpoint_url: form.endpointUrl,
      region: form.region,
      bucket_name: form.bucketName,
      prefix: form.prefix,
      upstream_config: upstreamConfigWithJetstream(
        {
          s3: {
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
      credentials: {
        access_key_id: form.accessKeyId,
        secret_access_key: form.secretAccessKey,
        ...(form.sessionToken
          ? {
              session_token: form.sessionToken,
            }
          : {}),
      },
    }

    try {
      await createBucket.mutateAsync(input)
      setForm(initialFormState)
      setOpen(false)
    } catch {
      // Error presentation is handled by the mutation's onError toast.
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <PlusIcon />
          {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <form onSubmit={handleSubmit} className="grid gap-5">
          <DialogHeader>
            <DialogTitle>Connect bucket</DialogTitle>
            <DialogDescription>
              Add an S3-compatible bucket connection. Credentials are encrypted
              by the API and are never returned in read responses.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Display name" htmlFor="bucket-name">
              <Input
                id="bucket-name"
                value={form.name}
                onChange={(event) => updateField("name", event.target.value)}
                placeholder="Production data"
                required
              />
            </Field>
            <Field label="Upstream" htmlFor="bucket-upstream">
              <Input id="bucket-upstream" value="S3-compatible" disabled />
            </Field>
            <Field label="Endpoint URL" htmlFor="endpoint-url">
              <Input
                id="endpoint-url"
                value={form.endpointUrl}
                onChange={(event) =>
                  updateField("endpointUrl", event.target.value)
                }
                placeholder="https://s3.amazonaws.com"
                required
              />
            </Field>
            <Field label="Region" htmlFor="region">
              <Input
                id="region"
                value={form.region}
                onChange={(event) => updateField("region", event.target.value)}
                placeholder="us-east-1"
                required
              />
            </Field>
            <Field label="Bucket name" htmlFor="upstream-bucket-name">
              <Input
                id="upstream-bucket-name"
                value={form.bucketName}
                onChange={(event) =>
                  updateField("bucketName", event.target.value)
                }
                placeholder="example-bucket"
                required
              />
            </Field>
            <Field label="Prefix" htmlFor="prefix">
              <Input
                id="prefix"
                value={form.prefix}
                onChange={(event) => updateField("prefix", event.target.value)}
                placeholder="raw/"
              />
            </Field>
          </div>

          <div className="grid gap-4 rounded-lg border bg-background/60 p-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <div className="text-sm font-medium">Credentials</div>
              <p className="mt-1 text-xs/6 text-muted-foreground">
                These fields are sent once to the API for encryption.
              </p>
            </div>
            <Field label="Access key ID" htmlFor="access-key-id">
              <Input
                id="access-key-id"
                value={form.accessKeyId}
                onChange={(event) =>
                  updateField("accessKeyId", event.target.value)
                }
                autoComplete="off"
                required
              />
            </Field>
            <Field label="Secret access key" htmlFor="secret-access-key">
              <Input
                id="secret-access-key"
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
              className="sm:col-span-2"
              label="Session token"
              htmlFor="session-token"
            >
              <Input
                id="session-token"
                type="password"
                value={form.sessionToken}
                onChange={(event) =>
                  updateField("sessionToken", event.target.value)
                }
                autoComplete="off"
                placeholder="Optional"
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
            idPrefix="create"
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

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={createBucket.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createBucket.isPending}>
              {createBucket.isPending ? "Connecting..." : "Connect bucket"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

type FieldProps = {
  children: React.ReactNode
  className?: string
  htmlFor: string
  label: string
}

function Field({ children, className, htmlFor, label }: FieldProps) {
  return (
    <div className={className}>
      <Label htmlFor={htmlFor}>{label}</Label>
      <div className="mt-1.5">{children}</div>
    </div>
  )
}
