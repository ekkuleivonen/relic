export function toStartOfDayIso(value: Date | undefined) {
  if (!value) return undefined
  const date = new Date(value)
  date.setHours(0, 0, 0, 0)
  return date.toISOString()
}

export function toEndOfDayIso(value: Date | undefined) {
  if (!value) return undefined
  const date = new Date(value)
  date.setHours(23, 59, 59, 999)
  return date.toISOString()
}
