export type Setting = {
  key: string
  value: string
  encrypted: boolean
  updated_at: string
  updated_by?: string | null
}

export type SettingsListResponse = {
  items: Setting[]
}

export type SettingPatchInput = {
  value: string
}
