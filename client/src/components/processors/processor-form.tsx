import * as React from "react"
import { ChevronsUpDownIcon, XIcon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import type {
  ProcessorCreateInput,
  ProcessorConfigSchema,
  ProcessorConfigSchemaProperty,
  ProcessorFolderOption,
  ProcessorFolderScope,
  ProcessorKind,
} from "@/types/processors"

type ProcessorFormProps = {
  processorKinds: ProcessorKind[]
  folders: ProcessorFolderOption[]
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (input: ProcessorCreateInput) => Promise<void> | void
}

type SelectOption = {
  value: string
  label: string
  description?: string
}

type ConfigValues = Record<string, unknown>

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
  const [selectedEventTypes, setSelectedEventTypes] = React.useState<
    string[] | null
  >(null)
  const [folderScopes, setFolderScopes] = React.useState<ProcessorFolderScope[]>(
    []
  )
  const [includeDescendants, setIncludeDescendants] = React.useState(true)
  const [selectedMimetypePrefixes, setSelectedMimetypePrefixes] = React.useState<
    string[] | null
  >(null)
  const [selectedExtensions, setSelectedExtensions] = React.useState<
    string[] | null
  >(null)
  const [configValues, setConfigValues] = React.useState<ConfigValues | null>(null)
  const [error, setError] = React.useState<string | null>(null)

  const effectiveKind = kind ?? processorKinds[0]?.kind ?? ""
  const selectedKind = processorKinds.find((item) => item.kind === effectiveKind)
  const eventOptions = React.useMemo(
    () =>
      (selectedKind?.event_type_options ?? []).map((option) => ({
        value: option.value,
        label: option.label,
        description: option.default ? "Default" : undefined,
      })),
    [selectedKind]
  )
  const folderOptions = React.useMemo(
    () =>
      folders.map((folder) => ({
        value: folder.id,
        label: folder.path,
        description: folder.name || "Root",
      })),
    [folders]
  )
  const mimetypeOptions = React.useMemo(
    () =>
      (selectedKind?.mimetype_filter_options ?? []).map((option) => ({
        value: option.value,
        label: option.label,
        description: option.default ? "Default" : undefined,
      })),
    [selectedKind]
  )
  const extensionOptions = React.useMemo(
    () =>
      (selectedKind?.extension_filter_options ?? []).map((option) => ({
        value: option.value,
        label: option.label,
        description: option.default ? "Default" : undefined,
      })),
    [selectedKind]
  )
  const selectedFolderIds = folderScopes.map((scope) => scope.folder_id)
  const effectiveEventTypes =
    selectedEventTypes ?? selectedKind?.default_subscribed_event_types ?? []
  const effectiveMimetypePrefixes =
    selectedMimetypePrefixes ?? selectedKind?.default_mimetype_prefixes ?? []
  const effectiveExtensions =
    selectedExtensions ?? selectedKind?.default_extensions ?? []
  const effectiveConfigValues =
    configValues ??
    (selectedKind ? defaultConfigValues(selectedKind.config_schema) : {})

  function handleKindChange(nextKind: string) {
    setKind(nextKind)
    setSelectedEventTypes(null)
    setSelectedMimetypePrefixes(null)
    setSelectedExtensions(null)
    setConfigValues(null)
    setError(null)
  }

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

    if (effectiveEventTypes.length === 0) {
      setError("Select at least one event type")
      return
    }

    let config: Record<string, unknown> | undefined
    try {
      config = selectedKind
        ? buildConfigFromSchema(selectedKind.config_schema, effectiveConfigValues)
        : undefined
    } catch (configError) {
      setError(
        configError instanceof Error
          ? configError.message
          : "Invalid processor config"
      )
      return
    }

    await onSubmit({
      name: name.trim(),
      kind: effectiveKind,
      enabled,
      subscribed_event_types: effectiveEventTypes,
      folder_scopes: folderScopes.length > 0 ? folderScopes : undefined,
      mimetype_prefixes:
        selectedMimetypePrefixes !== null ? selectedMimetypePrefixes : undefined,
      extensions:
        selectedExtensions !== null ? selectedExtensions : undefined,
      config,
    })
  }

  function setSelectedFolders(folderIds: string[]) {
    setFolderScopes((current) =>
      folderIds.map((folderId) => {
        const existing = current.find((scope) => scope.folder_id === folderId)
        return existing ?? { folder_id: folderId, cascade: includeDescendants }
      })
    )
  }

  function setCascadeForAll(value: boolean) {
    setIncludeDescendants(value)
    setFolderScopes((current) =>
      current.map((scope) => ({ ...scope, cascade: value }))
    )
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
          onValueChange={handleKindChange}
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
        <Label>Subscribed event types</Label>
        <SearchableMultiSelect
          options={eventOptions}
          values={effectiveEventTypes}
          onChange={setSelectedEventTypes}
          placeholder="Select event types"
          emptyText="No event types found."
          disabled={!selectedKind}
        />
        <p className="text-xs text-muted-foreground">
          Defaults are preselected for the processor kind.
        </p>
      </div>

      <div className="space-y-2">
        <Label>Folder filters</Label>
        <SearchableMultiSelect
          options={folderOptions}
          values={selectedFolderIds}
          onChange={setSelectedFolders}
          placeholder={
            folders.length === 0 ? "No folders available" : "Select folders"
          }
          emptyText="No folders found."
          disabled={folders.length === 0}
        />
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={includeDescendants}
            onCheckedChange={(value) => setCascadeForAll(value === true)}
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

      {mimetypeOptions.length > 0 && (
        <div className="space-y-2">
          <Label>Mimetype filters</Label>
          <SearchableMultiSelect
            options={mimetypeOptions}
            values={effectiveMimetypePrefixes}
            onChange={setSelectedMimetypePrefixes}
            placeholder="Select mimetype prefixes"
            emptyText="No mimetype prefixes available."
          />
          <p className="text-xs text-muted-foreground">
            Limits the processor to files whose detected mimetype starts with
            one of these prefixes. Defaults are preselected.
          </p>
        </div>
      )}

      {extensionOptions.length > 0 && (
        <div className="space-y-2">
          <Label>Extension filters</Label>
          <SearchableMultiSelect
            options={extensionOptions}
            values={effectiveExtensions}
            onChange={setSelectedExtensions}
            placeholder="Select extensions"
            emptyText="No extensions available."
          />
          <p className="text-xs text-muted-foreground">
            Files whose extension is not in this list are skipped.
          </p>
        </div>
      )}

      {selectedKind && (
        <ConfigSchemaForm
          schema={selectedKind.config_schema}
          values={effectiveConfigValues}
          onChange={setConfigValues}
        />
      )}

      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-sm">
          <Checkbox
            checked={enabled}
            onCheckedChange={(value) => setEnabled(value === true)}
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

function SearchableMultiSelect({
  options,
  values,
  onChange,
  placeholder,
  emptyText,
  disabled,
}: {
  options: SelectOption[]
  values: string[]
  onChange: (values: string[]) => void
  placeholder: string
  emptyText: string
  disabled?: boolean
}) {
  const [open, setOpen] = React.useState(false)
  const selected = options.filter((option) => values.includes(option.value))

  function toggle(value: string) {
    if (values.includes(value)) {
      onChange(values.filter((item) => item !== value))
      return
    }
    onChange([...values, value])
  }

  return (
    <div className="space-y-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            disabled={disabled}
            className="w-full justify-between font-normal"
          >
            <span
              className={cn(
                "truncate",
                selected.length === 0 && "text-muted-foreground"
              )}
            >
              {selected.length > 0
                ? `${selected.length} selected`
                : placeholder}
            </span>
            <ChevronsUpDownIcon className="opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent
          className="w-(--radix-popover-trigger-width) p-0"
          align="start"
        >
          <Command
            filter={(itemValue, search) =>
              itemValue.toLowerCase().includes(search.toLowerCase()) ? 1 : 0
            }
          >
            <CommandInput placeholder="Search options..." />
            <CommandList>
              <CommandEmpty>{emptyText}</CommandEmpty>
              <CommandGroup>
                {options.map((option) => {
                  const checked = values.includes(option.value)
                  return (
                    <CommandItem
                      key={option.value}
                      value={`${option.label} ${option.value}`}
                      data-checked={checked}
                      onSelect={() => toggle(option.value)}
                    >
                      <div className="min-w-0">
                        <div className="truncate font-mono text-xs">
                          {option.label}
                        </div>
                        {option.description && (
                          <div className="truncate text-[0.625rem] text-muted-foreground">
                            {option.description}
                          </div>
                        )}
                      </div>
                    </CommandItem>
                  )
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {selected.map((option) => (
            <Badge key={option.value} variant="outline">
              <span className="max-w-56 truncate font-mono">{option.label}</span>
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground"
                onClick={() => toggle(option.value)}
                aria-label={`Remove ${option.label}`}
              >
                <XIcon className="size-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}

function ConfigSchemaForm({
  schema,
  values,
  onChange,
}: {
  schema: ProcessorConfigSchema
  values: ConfigValues
  onChange: (values: ConfigValues) => void
}) {
  const properties = Object.entries(schema.properties ?? {})
  const required = new Set(schema.required ?? [])
  if (properties.length === 0) {
    return (
      <div className="rounded-md border bg-muted/20 p-3 text-xs text-muted-foreground">
        This processor kind has no configurable settings.
      </div>
    )
  }

  function setValue(key: string, value: unknown) {
    onChange({ ...values, [key]: value })
  }

  return (
    <div className="space-y-3">
      <div>
        <Label>Config</Label>
        {schema.description && (
          <p className="text-xs text-muted-foreground">{schema.description}</p>
        )}
      </div>
      {properties.map(([key, property]) => (
        <ConfigField
          key={key}
          fieldKey={key}
          property={property}
          required={required.has(key)}
          value={values[key]}
          onChange={(value) => setValue(key, value)}
        />
      ))}
    </div>
  )
}

function ConfigField({
  fieldKey,
  property,
  required,
  value,
  onChange,
}: {
  fieldKey: string
  property: ProcessorConfigSchemaProperty
  required: boolean
  value: unknown
  onChange: (value: unknown) => void
}) {
  const type = schemaPropertyType(property)
  const label = property.title ?? titleize(fieldKey)
  const id = `processor-config-${fieldKey}`

  if (type === "boolean") {
    return (
      <label className="flex items-start gap-2 text-sm">
        <Checkbox
          id={id}
          checked={value === true}
          onCheckedChange={(checked) => onChange(checked === true)}
        />
        <span>
          {label}
          {property.description && (
            <span className="block text-xs text-muted-foreground">
              {property.description}
            </span>
          )}
        </span>
      </label>
    )
  }

  if (type === "object") {
    return (
      <div className="space-y-2">
        <FieldLabel id={id} label={label} required={required} />
        <Textarea
          id={id}
          value={typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2)}
          onChange={(event) => onChange(event.target.value)}
          rows={4}
          placeholder="{}"
        />
        <FieldDescription property={property} />
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <FieldLabel id={id} label={label} required={required} />
      <Input
        id={id}
        value={value == null ? "" : String(value)}
        onChange={(event) => onChange(event.target.value)}
        type={inputType(property, type)}
        min={property.minimum}
        max={property.maximum}
        minLength={property.minLength}
        maxLength={property.maxLength}
        required={required}
      />
      <FieldDescription property={property} />
    </div>
  )
}

function FieldLabel({
  id,
  label,
  required,
}: {
  id: string
  label: string
  required: boolean
}) {
  return (
    <Label htmlFor={id}>
      {label}
      {required && <span className="text-destructive"> *</span>}
    </Label>
  )
}

function FieldDescription({
  property,
}: {
  property: ProcessorConfigSchemaProperty
}) {
  if (!property.description) {
    return null
  }
  return <p className="text-xs text-muted-foreground">{property.description}</p>
}

function FolderScopeList({
  scopes,
  folders,
  onRemove,
}: {
  scopes: ProcessorFolderScope[]
  folders: ProcessorFolderOption[]
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

function schemaPropertyType(property: ProcessorConfigSchemaProperty): string {
  if (Array.isArray(property.type)) {
    return property.type.find((item) => item !== "null") ?? "string"
  }
  return property.type ?? "string"
}

function inputType(
  property: ProcessorConfigSchemaProperty,
  schemaType: string
): React.HTMLInputTypeAttribute {
  if (property.writeOnly || property.format === "password") {
    return "password"
  }
  if (schemaType === "integer" || schemaType === "number") {
    return "number"
  }
  if (property.format === "uri") {
    return "url"
  }
  return "text"
}

function defaultConfigValues(schema: ProcessorConfigSchema): ConfigValues {
  const values: ConfigValues = {}
  for (const [key, property] of Object.entries(schema.properties ?? {})) {
    const type = schemaPropertyType(property)
    if (property.default !== undefined) {
      values[key] =
        type === "object"
          ? JSON.stringify(property.default, null, 2)
          : property.default
    } else if (type === "object") {
      values[key] = "{}"
    } else if (type === "boolean") {
      values[key] = false
    } else {
      values[key] = ""
    }
  }
  return values
}

function buildConfigFromSchema(
  schema: ProcessorConfigSchema,
  values: ConfigValues
): Record<string, unknown> | undefined {
  const properties = Object.entries(schema.properties ?? {})
  if (properties.length === 0) {
    return undefined
  }
  const required = new Set(schema.required ?? [])
  const config: Record<string, unknown> = {}

  for (const [key, property] of properties) {
    const type = schemaPropertyType(property)
    const raw = values[key]
    if (raw === "" || raw === undefined || raw === null) {
      if (required.has(key)) {
        throw new Error(`${property.title ?? titleize(key)} is required`)
      }
      continue
    }

    if (type === "object") {
      try {
        const parsed = typeof raw === "string" ? JSON.parse(raw) : raw
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          throw new Error("must be a JSON object")
        }
        config[key] = parsed
      } catch (error) {
        const message = error instanceof Error ? error.message : "invalid JSON"
        throw new Error(`${property.title ?? titleize(key)} ${message}`)
      }
      continue
    }

    if (type === "integer" || type === "number") {
      const value = Number(raw)
      if (!Number.isFinite(value)) {
        throw new Error(`${property.title ?? titleize(key)} must be a number`)
      }
      if (property.minimum !== undefined && value < property.minimum) {
        throw new Error(
          `${property.title ?? titleize(key)} must be at least ${property.minimum}`
        )
      }
      if (
        property.exclusiveMinimum !== undefined &&
        value <= property.exclusiveMinimum
      ) {
        throw new Error(
          `${property.title ?? titleize(key)} must be greater than ${property.exclusiveMinimum}`
        )
      }
      if (property.maximum !== undefined && value > property.maximum) {
        throw new Error(
          `${property.title ?? titleize(key)} must be at most ${property.maximum}`
        )
      }
      if (
        property.exclusiveMaximum !== undefined &&
        value >= property.exclusiveMaximum
      ) {
        throw new Error(
          `${property.title ?? titleize(key)} must be less than ${property.exclusiveMaximum}`
        )
      }
      config[key] = type === "integer" ? Math.trunc(value) : value
      continue
    }

    if (type === "boolean") {
      config[key] = raw === true
      continue
    }

    const value = String(raw)
    if (property.minLength !== undefined && value.length < property.minLength) {
      throw new Error(
        `${property.title ?? titleize(key)} must be at least ${property.minLength} characters`
      )
    }
    if (property.maxLength !== undefined && value.length > property.maxLength) {
      throw new Error(
        `${property.title ?? titleize(key)} must be at most ${property.maxLength} characters`
      )
    }
    config[key] = value
  }

  return config
}

function titleize(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
}
