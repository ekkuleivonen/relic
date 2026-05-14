export type Processor = {
  id: string
  name: string
  kind: string
  enabled: boolean
  source: "seed" | "admin"
  subscribed_event_types: string[]
  folder_scopes: ProcessorFolderScope[]
  config: Record<string, unknown>
  last_committed_offset: number
  last_committed_at: string | null
  last_failed_event_id: string | null
  last_failed_at: string | null
  last_error_class: string | null
  last_error_message: string | null
  head_offset: number
  pending_count: number
  created_at: string
  updated_at: string
}

export type ProcessorFolderScope = {
  folder_id: string
  cascade: boolean
}

export type ProcessorListResponse = {
  items: Processor[]
  total: number
  limit: number
  offset: number
}

export type ProcessorKind = {
  kind: string
  display_name: string
  description: string
  default_task_queue: string
  default_concurrency: number
  max_concurrency: number
  default_subscribed_event_types: string[]
  valid_event_types: string[]
  event_type_options: ProcessorEventTypeOption[]
  config_schema: ProcessorConfigSchema
}

export type ProcessorKindsResponse = {
  items: ProcessorKind[]
}

export type ProcessorEventTypeOption = {
  value: string
  label: string
  default: boolean
}

export type ProcessorFolderOption = {
  id: string
  name: string
  path: string
}

export type ProcessorFolderOptionsResponse = {
  items: ProcessorFolderOption[]
}

export type ProcessorConfigSchema = {
  title?: string
  description?: string
  type?: string
  required?: string[]
  properties?: Record<string, ProcessorConfigSchemaProperty>
}

export type ProcessorConfigSchemaProperty = {
  title?: string
  description?: string
  type?: string | string[]
  format?: string
  default?: unknown
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
  exclusiveMinimum?: number
  exclusiveMaximum?: number
  writeOnly?: boolean
  additionalProperties?: boolean | ProcessorConfigSchemaProperty
}

export type ProcessorCreateInput = {
  name: string
  kind: string
  enabled?: boolean
  subscribed_event_types?: string[]
  folder_scopes?: ProcessorFolderScope[]
  config?: Record<string, unknown>
}

export type ProcessorUpdateInput = {
  enabled?: boolean
  subscribed_event_types?: string[]
  folder_scopes?: ProcessorFolderScope[]
  config?: Record<string, unknown>
}

export type ProcessorRewindInput = {
  target_offset: number
  reason: string
}

export type ProcessorSkipInput = {
  event_id: string
  reason: string
}
