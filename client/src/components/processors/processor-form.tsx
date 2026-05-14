import * as React from "react"

import { FolderCombobox } from "@/components/folder-access/folder-combobox"
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
import type { FolderPathEntry } from "@/lib/folder-path"
import type {
  ProcessorCreateInput,
  ProcessorFolderScope,
  ProcessorKind,
} from "@/types/processors"

type ProcessorFormProps = {
  processorKinds: ProcessorKind[]
  folders: FolderPathEntry[]
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (input: ProcessorCreateInput) => Promise<void> | void
}

export function ProcessorForm({
  processorKinds,
  folders,
  isSubmitting,
  onCancel,
  onSubmit,
}: ProcessorFormProps) {
  const [name, setName] = React.useState("")
  const [kind, setKind] = React.useState<string | undefined>(undefined)
  const [enabled, setEnabled] = React.useState(true)
  const [subscribedTypesRaw, setSubscribedTypesRaw] = React.useState("")
  const [folderScopes, setFolderScopes] = React.useState<ProcessorFolderScope[]>(
    []
  )
  const [selectedFolderId, setSelectedFolderId] = React.useState("")
  const [cascade, setCascade] = React.useState(true)
  const [configRaw, setConfigRaw] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)

  const effectiveKind = kind ?? processorKinds[0]?.kind ?? ""
  const selectedKind = processorKinds.find((item) => item.kind === effectiveKind)

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
      folder_scopes: folderScopes.length > 0 ? folderScopes : undefined,
      config,
    })
  }

  function addFolderScope() {
    if (!selectedFolderId) {
      setError("Choose a folder scope before adding it")
      return
    }
    setError(null)
    setFolderScopes((current) => {
      const existing = current.find((scope) => scope.folder_id === selectedFolderId)
      if (existing) {
        return current.map((scope) =>
          scope.folder_id === selectedFolderId
            ? { ...scope, cascade: scope.cascade || cascade }
            : scope
        )
      }
      return [...current, { folder_id: selectedFolderId, cascade }]
    })
    setSelectedFolderId("")
    setCascade(true)
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
          disabled={processorKinds.length === 0}
        >
          <SelectTrigger id="processor-kind" className="w-full">
            <SelectValue placeholder="Choose a processor kind" />
          </SelectTrigger>
          <SelectContent>
            {processorKinds.map((processorKind) => (
              <SelectItem key={processorKind.kind} value={processorKind.kind}>
                {processorKind.display_name || processorKind.kind}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {selectedKind && (
          <p className="text-xs text-muted-foreground">
            Queue <code>{selectedKind.default_task_queue}</code>, default
            concurrency {selectedKind.default_concurrency}.
          </p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="processor-types">Subscribed event types</Label>
        <Input
          id="processor-types"
          value={subscribedTypesRaw}
          onChange={(event) => setSubscribedTypesRaw(event.target.value)}
          placeholder="leave blank for processor defaults"
          autoComplete="off"
        />
        <p className="text-xs text-muted-foreground">
          Comma- or space-separated. Empty falls back to the processor kind's defaults.
        </p>
      </div>

      <div className="space-y-2">
        <Label>Folder scopes</Label>
        <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
          <FolderCombobox
            folders={folders}
            value={selectedFolderId || undefined}
            onChange={setSelectedFolderId}
            disabled={folders.length === 0}
            placeholder={
              folders.length === 0 ? "No folders available" : "Select a folder"
            }
          />
          <Button type="button" variant="outline" onClick={addFolderScope}>
            Add Scope
          </Button>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={cascade}
            onChange={(event) => setCascade(event.target.checked)}
            className="size-4"
          />
          Include descendants
        </label>
        <FolderScopeList
          scopes={folderScopes}
          folders={folders}
          onRemove={(folderId) =>
            setFolderScopes((current) =>
              current.filter((scope) => scope.folder_id !== folderId)
            )
          }
        />
        <p className="text-xs text-muted-foreground">
          Empty means this processor receives matching events from every folder.
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

function FolderScopeList({
  scopes,
  folders,
  onRemove,
}: {
  scopes: ProcessorFolderScope[]
  folders: FolderPathEntry[]
  onRemove: (folderId: string) => void
}) {
  if (scopes.length === 0) {
    return null
  }
  return (
    <div className="flex flex-wrap gap-2">
      {scopes.map((scope) => {
        const folder = folders.find((entry) => entry.id === scope.folder_id)
        return (
          <div
            key={scope.folder_id}
            className="flex items-center gap-2 rounded-md border px-2 py-1 text-xs"
          >
            <span className="font-mono">
              {folder?.path ?? scope.folder_id}
              {scope.cascade ? "/*" : ""}
            </span>
            <button
              type="button"
              className="text-muted-foreground hover:text-foreground"
              onClick={() => onRemove(scope.folder_id)}
            >
              Remove
            </button>
          </div>
        )
      })}
    </div>
  )
}
