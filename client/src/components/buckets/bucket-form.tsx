import * as React from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { Bucket, BucketCreateInput } from "@/types/buckets"

type BucketFormProps = {
  bucketRecord?: Bucket
  submitLabel: string
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (values: BucketCreateInput) => Promise<void>
}

type FieldLabelProps = {
  htmlFor?: string
  label: string
  tooltip: string
}

type BucketFormValues = Omit<BucketCreateInput, "max_size_bytes">

export function BucketForm({
  bucketRecord,
  submitLabel,
  isSubmitting,
  onCancel,
  onSubmit,
}: BucketFormProps) {
  const [values, setValues] = React.useState<BucketFormValues>(() => ({
    name: bucketRecord?.name ?? "",
    endpoint: bucketRecord?.endpoint ?? "",
    region: bucketRecord?.region ?? "",
    bucket: bucketRecord?.bucket ?? "",
    key_id: bucketRecord?.key_id ?? "",
    secret_access_key: bucketRecord?.secret_access_key ?? "",
  }))
  const [maxSizeValue, setMaxSizeValue] = React.useState(() =>
    bucketRecord ? String(bucketRecord.max_size_bytes / 1_000_000_000) : ""
  )
  const [maxSizeUnit, setMaxSizeUnit] = React.useState<SizeUnit | "">(
    bucketRecord ? "GB" : ""
  )

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (maxSizeUnit === "") {
      return
    }

    await onSubmit({
      ...values,
      max_size_bytes: toBytes(Number(maxSizeValue), maxSizeUnit),
    })
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="grid gap-2">
        <FieldLabel
          htmlFor="bucket-name"
          label="Name"
          tooltip="Human-readable label for this bucket backend in the admin UI."
        />
        <Input
          id="bucket-name"
          placeholder="garage-hot"
          value={values.name}
          onChange={(event) =>
            setValues((current) => ({ ...current, name: event.target.value }))
          }
          required
        />
      </div>

      <div className="grid gap-2">
        <FieldLabel
          htmlFor="bucket-endpoint"
          label="Endpoint"
          tooltip="Base S3-compatible endpoint as seen by the API server. In Docker Compose, use http://garage-hot:3900 rather than localhost."
        />
        <Input
          id="bucket-endpoint"
          placeholder="http://garage-hot:3900"
          value={values.endpoint}
          onChange={(event) =>
            setValues((current) => ({
              ...current,
              endpoint: event.target.value,
            }))
          }
          required
        />
      </div>

      <div className="grid gap-2">
        <FieldLabel
          htmlFor="bucket-region"
          label="Region"
          tooltip="S3 signing region expected by the remote bucket."
        />
        <Input
          id="bucket-region"
          placeholder="garage"
          value={values.region}
          onChange={(event) =>
            setValues((current) => ({ ...current, region: event.target.value }))
          }
          required
        />
      </div>

      <div className="grid gap-2">
        <FieldLabel
          htmlFor="bucket-name-remote"
          label="Bucket"
          tooltip="Single remote bucket Relic writes blobs into."
        />
        <Input
          id="bucket-name-remote"
          placeholder="blobs"
          value={values.bucket}
          onChange={(event) =>
            setValues((current) => ({ ...current, bucket: event.target.value }))
          }
          required
        />
      </div>

      <div className="grid gap-2">
        <FieldLabel
          htmlFor="bucket-key-id"
          label="Key ID"
          tooltip="Access key ID used when Relic talks to this remote bucket. Stored encrypted."
        />
        <Input
          id="bucket-key-id"
          placeholder="GK..."
          value={values.key_id}
          onChange={(event) =>
            setValues((current) => ({
              ...current,
              key_id: event.target.value,
            }))
          }
          required
        />
      </div>

      <div className="grid gap-2">
        <FieldLabel
          htmlFor="bucket-secret-access-key"
          label="Secret Access Key"
          tooltip="Secret half of the S3 credential pair. Stored encrypted at rest."
        />
        <Input
          id="bucket-secret-access-key"
          type="password"
          placeholder="Secret access key"
          value={values.secret_access_key}
          onChange={(event) =>
            setValues((current) => ({
              ...current,
              secret_access_key: event.target.value,
            }))
          }
          required
        />
      </div>

      <div className="grid gap-2">
        <FieldLabel
          htmlFor="bucket-max-size"
          label="Max Size"
          tooltip="User-provided write limit for this bucket. Relic derives usage from stored blobs when placing new data."
        />
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <Input
            id="bucket-max-size"
            type="number"
            min={0}
            step="0.1"
            placeholder="1"
            value={maxSizeValue}
            onChange={(event) => {
              setMaxSizeValue(event.target.value)
            }}
            required
          />
          <Select
            value={maxSizeUnit === "" ? undefined : maxSizeUnit}
            onValueChange={(value) => {
              const unit = value as SizeUnit
              setMaxSizeUnit(unit)
            }}
          >
            <SelectTrigger>
              <SelectValue placeholder="Unit" />
            </SelectTrigger>
            <SelectContent>
              {sizeUnits.map((unit) => (
                <SelectItem key={unit} value={unit}>
                  {unit}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : submitLabel}
        </Button>
      </div>
    </form>
  )
}

const sizeUnits = ["MB", "GB", "TB", "PB"] as const
type SizeUnit = (typeof sizeUnits)[number]

const sizeUnitMultipliers: Record<SizeUnit, number> = {
  MB: 1_000_000,
  GB: 1_000_000_000,
  TB: 1_000_000_000_000,
  PB: 1_000_000_000_000_000,
}

function toBytes(value: number, unit: SizeUnit) {
  return Math.round(value * sizeUnitMultipliers[unit])
}

function FieldLabel({ htmlFor, label, tooltip }: FieldLabelProps) {
  return (
    <div className="flex items-center gap-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            className="text-xs text-muted-foreground underline decoration-dotted underline-offset-4 hover:text-foreground"
            aria-label={`${label} help`}
          >
            ?
          </button>
        </TooltipTrigger>
        <TooltipContent side="right">{tooltip}</TooltipContent>
      </Tooltip>
    </div>
  )
}
