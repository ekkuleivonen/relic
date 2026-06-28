import type { JobRun } from "@/types/job-runs"

export function objectCountFromJobRun(jobRun: JobRun) {
  const objects = jobRun.input.objects
  if (Array.isArray(objects)) {
    return objects.length
  }

  const progressCount = jobRun.progress.objects_processed
  if (typeof progressCount === "number") {
    return progressCount
  }

  return 0
}

export function objectKeysFromJobRun(jobRun: JobRun, limit = 20) {
  const objects = jobRun.input.objects
  if (!Array.isArray(objects)) {
    return []
  }

  return objects
    .slice(0, limit)
    .map((entry) => {
      if (entry && typeof entry === "object" && "key" in entry) {
        const key = (entry as { key?: unknown }).key
        return typeof key === "string" ? key : null
      }

      return null
    })
    .filter((key): key is string => Boolean(key))
}
