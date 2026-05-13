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
import { Textarea } from "@/components/ui/textarea"
import type {
  ProcessorCreateInput,
  ProcessorSubstrate,
} from "@/types/processors"

type ProcessorFormProps = {
  substrates: ProcessorSubstrate[]
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (input: ProcessorCreateInput) => Promise<void> | void
}

export function ProcessorForm({
  substrates,
  isSubmitting,
  onCancel,
  onSubmit,
}: ProcessorFormProps) {
  const [name, setName] = React.useState("")
  const [kind, setKind] = React.useState<string | undefined>(undefined)
  const [enabled, setEnabled] = React.useState(true)
  const [subscribedTypesRaw, setSubscribedTypesRaw] = React.useState("")
  const [configRaw, setConfigRaw] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)

  const effectiveKind = kind ?? substrates[0]?.kind ?? ""

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    if (!name.trim()) {
      setError("Name is required")
      return
    }
    if (!effectiveKind) {
      setError("Kind is required")
      return
    }

    let subscribed: string[] | undefined
    const cleanedTypes = subscribedTypesRaw.trim()
    if (cleanedTypes) {
      subscribed = cleanedTypes
        .split(/[\s,]+/)
        .map((value) => value.trim())
        .filter(Boolean)
    }

    let config: Record<string, unknown> | undefined
    const cleanedConfig = configRaw.trim()
    if (cleanedConfig) {
      try {
        const parsed = JSON.parse(cleanedConfig)
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          throw new Error("config must be a JSON object")
        }
        config = parsed as Record<string, unknown>
      } catch (parseError) {
        setError(
          parseError instanceof Error
            ? `Invalid config JSON: ${parseError.message}`
            : "Invalid config JSON"
        )
        return
      }
    }

    await onSubmit({
      name: name.trim(),
      kind: effectiveKind,
      enabled,
      subscribed_event_types: subscribed,
      config,
    })
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="space-y-2">
        <Label htmlFor="processor-name">Name</Label>
        <Input
          id="processor-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="webhook:acme"
          autoComplete="off"
          required
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="processor-kind">Kind</Label>
        <Select
          value={effectiveKind || undefined}
          onValueChange={setKind}
          disabled={substrates.length === 0}
        >
          <SelectTrigger id="processor-kind" className="w-full">
            <SelectValue placeholder="Choose a substrate" />
          </SelectTrigger>
          <SelectContent>
            {substrates.map((substrate) => (
              <SelectItem key={substrate.kind} value={substrate.kind}>
                {substrate.kind}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="processor-types">Subscribed event types</Label>
        <Input
          id="processor-types"
          value={subscribedTypesRaw}
          onChange={(event) => setSubscribedTypesRaw(event.target.value)}
          placeholder="leave blank for substrate defaults"
          autoComplete="off"
        />
        <p className="text-xs text-muted-foreground">
          Comma- or space-separated. Empty falls back to the substrate's defaults.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="processor-config">Config (JSON)</Label>
        <Textarea
          id="processor-config"
          value={configRaw}
          onChange={(event) => setConfigRaw(event.target.value)}
          rows={4}
          placeholder='{"webhook_url": "https://..."}'
        />
      </div>

      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
            className="size-4"
          />
          Enabled on creation
        </label>
        <span className="text-xs text-muted-foreground">
          You can pause it later via the table actions.
        </span>
      </div>

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Creating..." : "Create"}
        </Button>
      </div>
    </form>
  )
}
