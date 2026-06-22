import * as React from "react"

import { Badge } from "@/components/ui/badge"
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
import {
  buildStorageBackendCreatePayload,
  storageBackendKindLabel,
} from "@/lib/storage-backends"
import type {
  StorageBackend,
  StorageBackendCreateInput,
  StorageBackendKind,
} from "@/types/storage-backends"

type StorageBackendFormProps = {
  storageBackend?: StorageBackend
  submitLabel: string
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (values: StorageBackendCreateInput) => Promise<void>
}

type FieldLabelProps = {
  htmlFor?: string
  label: string
  tooltip: string
}

type StorageBackendFormValues = {
  name: string
  endpoint: string
  region: string
  namespace: string
  key_id: string
  secret_access_key: string
  kind: StorageBackendKind
}

const creatableKinds: StorageBackendKind[] = ["s3", "filesystem"]

export function StorageBackendForm({
  storageBackend,
  submitLabel,
  isSubmitting,
  onCancel,
  onSubmit,
}: StorageBackendFormProps) {
  const isEdit = storageBackend !== undefined
  const [values, setValues] = React.useState<StorageBackendFormValues>(() => ({
    name: storageBackend?.name ?? "",
    endpoint: storageBackend?.endpoint ?? "",
    region: storageBackend?.region ?? "",
    namespace: storageBackend?.namespace ?? "",
    key_id: "",
    secret_access_key: "",
    kind: storageBackend?.kind ?? "s3",
  }))
  const [maxSizeValue, setMaxSizeValue] = React.useState(() =>
    storageBackend ? String(storageBackend.max_size_bytes / 1_000_000_000) : ""
  )
  const [maxSizeUnit, setMaxSizeUnit] = React.useState<SizeUnit | "">(
    storageBackend ? "GB" : ""
  )

  const isFilesystem = values.kind === "filesystem"

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (maxSizeUnit === "") {
      return
    }

    await onSubmit(
      buildStorageBackendCreatePayload(
        values,
        toBytes(Number(maxSizeValue), maxSizeUnit)
      )
    )
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="grid gap-2">
        <FieldLabel
          htmlFor="storage-backend-kind"
          label="Storage kind"
          tooltip="S3-compatible remote storage or a local directory on the API server."
        />
        {isEdit ? (
          <div className="flex h-9 items-center">
            <Badge variant="outline">
              {storageBackendKindLabel(values.kind)}
            </Badge>
          </div>
        ) : (
          <Select
            value={values.kind}
            onValueChange={(value) =>
              setValues((current) => ({
                ...current,
                kind: value as StorageBackendKind,
              }))
            }
          >
            <SelectTrigger id="storage-backend-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="s3">S3-compatible</SelectItem>
              <SelectItem value="filesystem">Filesystem</SelectItem>
              <SelectItem value="azure_blob" disabled>
                Azure Blob (coming soon)
              </SelectItem>
              <SelectItem value="gcs" disabled>
                GCS (coming soon)
              </SelectItem>
            </SelectContent>
          </Select>
        )}
      </div>

      <div className="grid gap-2">
        <FieldLabel
          htmlFor="storage-backend-name"
          label="Name"
          tooltip="Human-readable label for this storage backend in the admin UI."
        />
        <Input
          id="storage-backend-name"
          placeholder={isFilesystem ? "hot-nvme" : "garage-hot"}
          value={values.name}
          onChange={(event) =>
            setValues((current) => ({ ...current, name: event.target.value }))
          }
          required
        />
      </div>

      <div className="grid gap-2">
        <FieldLabel
          htmlFor="storage-backend-endpoint"
          label={isFilesystem ? "Base path" : "Endpoint"}
          tooltip={
            isFilesystem
              ? "Absolute directory path visible to the API process. Docker Compose mounts filesystem_data at /var/relic/storage — use that path, not a host path."
              : "Base S3-compatible endpoint as seen by the API server. In Docker Compose, use http://garage-hot:3900 rather than localhost."
          }
        />
        <Input
          id="storage-backend-endpoint"
          placeholder={isFilesystem ? "/var/relic/storage" : "http://garage-hot:3900"}
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

      {!isFilesystem ? (
        <>
          <div className="grid gap-2">
            <FieldLabel
              htmlFor="storage-backend-region"
              label="Region"
              tooltip="S3 signing region expected by the remote storage."
            />
            <Input
              id="storage-backend-region"
              placeholder="garage"
              value={values.region}
              onChange={(event) =>
                setValues((current) => ({
                  ...current,
                  region: event.target.value,
                }))
              }
              required
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel
              htmlFor="storage-backend-namespace"
              label="Namespace"
              tooltip="Single remote namespace Relic writes blobs into."
            />
            <Input
              id="storage-backend-namespace"
              placeholder="blobs"
              value={values.namespace}
              onChange={(event) =>
                setValues((current) => ({
                  ...current,
                  namespace: event.target.value,
                }))
              }
              required
            />
          </div>

          <div className="grid gap-2">
            <FieldLabel
              htmlFor="storage-backend-key-id"
              label="Key ID"
              tooltip="Access key ID used when Relic talks to this remote storage. Stored encrypted."
            />
            <Input
              id="storage-backend-key-id"
              placeholder={isEdit ? "Leave blank to keep current key ID" : "GK..."}
              value={values.key_id}
              onChange={(event) =>
                setValues((current) => ({
                  ...current,
                  key_id: event.target.value,
                }))
              }
              required={!isEdit}
            />
            {isEdit && storageBackend ? (
              <p className="text-xs text-muted-foreground">
                Configured key ID: {storageBackend.key_id}
              </p>
            ) : null}
          </div>

          <div className="grid gap-2">
            <FieldLabel
              htmlFor="storage-backend-secret-access-key"
              label="Secret Access Key"
              tooltip="Secret half of the S3 credential pair. Stored encrypted at rest."
            />
            <Input
              id="storage-backend-secret-access-key"
              type="password"
              placeholder={
                isEdit ? "Leave blank to keep current secret" : "Secret access key"
              }
              value={values.secret_access_key}
              onChange={(event) =>
                setValues((current) => ({
                  ...current,
                  secret_access_key: event.target.value,
                }))
              }
              required={!isEdit}
            />
          </div>
        </>
      ) : (
        <div className="grid gap-2">
          <FieldLabel
            htmlFor="storage-backend-subdirectory"
            label="Subdirectory"
            tooltip="Folder name under the base path where blob objects are stored, for example blobs."
          />
          <Input
            id="storage-backend-subdirectory"
            placeholder="blobs"
            value={values.namespace}
            onChange={(event) =>
              setValues((current) => ({
                ...current,
                namespace: event.target.value,
              }))
            }
            required
          />
        </div>
      )}

      <div className="grid gap-2">
        <FieldLabel
          htmlFor="storage-backend-max-size"
          label="Max Size"
          tooltip="User-provided write limit for this backend. Relic derives usage from stored blobs when placing new data."
        />
        <div className="grid grid-cols-[1fr_auto] gap-2">
          <Input
            id="storage-backend-max-size"
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
        <Button
          type="submit"
          disabled={
            isSubmitting ||
            (!isEdit && !creatableKinds.includes(values.kind))
          }
        >
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
