export function formatBytes(bytes: number | undefined) {
  if (bytes === undefined) {
    return "Unknown"
  }
  if (bytes === 0) {
    return "0 B"
  }
  const units = ["B", "KB", "MB", "GB", "TB"] as const
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1
  )
  const value = bytes / 1024 ** exponent
  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`
}

export function formatRelativeTime(value: string | undefined): string {
  if (!value) {
    return "—"
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return "—"
  }
  const diffMs = Date.now() - date.getTime()
  const seconds = Math.round(diffMs / 1000)
  const absSeconds = Math.abs(seconds)
  if (absSeconds < 60) return "just now"
  const minutes = Math.round(seconds / 60)
  if (Math.abs(minutes) < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (Math.abs(days) < 30) return `${days}d ago`
  return date.toLocaleDateString()
}
