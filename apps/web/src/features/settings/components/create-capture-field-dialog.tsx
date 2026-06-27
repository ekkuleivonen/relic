import * as React from "react"
import { PlusIcon } from "lucide-react"

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  USER_CAPTURE_SOURCES,
  USER_VALUE_TYPES,
  defaultExtractorType,
  extractorRefHelp,
  extractorRefHint,
  extractorTypesForSource,
  formatCaptureSource,
  formatExtractorType,
} from "@/features/settings/lib/upstream-capture-options"
import { useCreateUpstreamCaptureField } from "@/features/settings/hooks/use-upstream-capture-fields"
import type {
  CaptureExtractorType,
  CaptureSource,
  CaptureValueType,
  CreateUpstreamCaptureFieldInput,
} from "@/types/upstream-capture"

const initialFormState = {
  attributePath: "upstream.",
  captureSource: "head" as CaptureSource,
  extractorType: "response_header" as CaptureExtractorType,
  extractorRef: "",
  valueType: "string" as CaptureValueType,
}

export function CreateCaptureFieldDialog() {
  const [open, setOpen] = React.useState(false)
  const [form, setForm] = React.useState(initialFormState)
  const createField = useCreateUpstreamCaptureField()

  function updateCaptureSource(captureSource: CaptureSource) {
    setForm((current) => ({
      ...current,
      captureSource,
      extractorType: defaultExtractorType(captureSource),
    }))
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const input: CreateUpstreamCaptureFieldInput = {
      attribute_path: form.attributePath.trim(),
      enabled: true,
      capture_source: form.captureSource,
      extractor_type: form.extractorType,
      extractor_ref: form.extractorRef.trim(),
      value_type: form.valueType,
    }

    try {
      await createField.mutateAsync(input)
      setForm(initialFormState)
      setOpen(false)
    } catch {
      // Toast handled by mutation onError.
    }
  }

  const extractorOptions = extractorTypesForSource(form.captureSource)

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <PlusIcon />
          Add capture field
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-xl">
        <form onSubmit={handleSubmit} className="grid gap-5">
          <DialogHeader>
            <DialogTitle>Add capture field</DialogTitle>
            <DialogDescription>
              Map a S3 HEAD response header, metadata key, or object tag to an{" "}
              <span className="font-mono">upstream.*</span> attribute path. Policy
              applies instance-wide on import and refresh.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4">
            <Field label="Attribute path" htmlFor="capture-attribute-path">
              <Input
                id="capture-attribute-path"
                value={form.attributePath}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    attributePath: event.target.value,
                  }))
                }
                placeholder="upstream.vendor.deployment_id"
                className="font-mono"
                required
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Capture source" htmlFor="capture-source">
                <Select
                  value={form.captureSource}
                  onValueChange={(value) =>
                    updateCaptureSource(value as CaptureSource)
                  }
                >
                  <SelectTrigger id="capture-source" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {USER_CAPTURE_SOURCES.map((source) => (
                      <SelectItem key={source} value={source}>
                        {formatCaptureSource(source)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <Field label="Extractor type" htmlFor="capture-extractor-type">
                <Select
                  value={form.extractorType}
                  onValueChange={(value) =>
                    setForm((current) => ({
                      ...current,
                      extractorType: value as CaptureExtractorType,
                    }))
                  }
                >
                  <SelectTrigger id="capture-extractor-type" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {extractorOptions.map((extractorType) => (
                      <SelectItem key={extractorType} value={extractorType}>
                        {formatExtractorType(extractorType)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </div>

            <Field label="Extractor ref" htmlFor="capture-extractor-ref">
              <Input
                id="capture-extractor-ref"
                value={form.extractorRef}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    extractorRef: event.target.value,
                  }))
                }
                placeholder={extractorRefHint(form.extractorType)}
                className="font-mono"
                required
              />
              <p className="mt-1.5 text-xs/6 text-muted-foreground">
                {extractorRefHelp(form.extractorType)}
              </p>
            </Field>

            <Field label="Value type" htmlFor="capture-value-type">
              <Select
                value={form.valueType}
                onValueChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    valueType: value as CaptureValueType,
                  }))
                }
              >
                <SelectTrigger id="capture-value-type" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {USER_VALUE_TYPES.map((valueType) => (
                    <SelectItem key={valueType} value={valueType}>
                      {valueType}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={createField.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createField.isPending}>
              Add field
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string
  htmlFor: string
  children: React.ReactNode
}) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  )
}
