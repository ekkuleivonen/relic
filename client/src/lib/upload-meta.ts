export type UploadMetaRow = {
  id: string
  key: string
  value: string
}

export function emptyUploadMetaRow(): UploadMetaRow {
  return { id: `row-${Date.now()}`, key: "", value: "" }
}

export function buildUploadMetaRecord(
  rows: UploadMetaRow[]
): Record<string, string> {
  const out: Record<string, string> = {}
  for (const row of rows) {
    const key = row.key.trim()
    if (!key) continue
    out[key] = row.value
  }
  return out
}

export const UPLOAD_META_HINT =
  "Optional. Applied to every file in this upload. Values are stored as text (S3 user metadata). Edit nested metadata after upload via the file detail page."
