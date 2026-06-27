import type { User } from "@/types/auth"
import { formatJobRunType } from "@/features/job-runs/components/job-run-format"
import type { JobRunType } from "@/types/job-runs"

export function isUserProvenanceRef(ref: string) {
  return ref.startsWith("user_")
}

export function isJobRunProvenanceRef(ref: string) {
  return ref.startsWith("jobrun_")
}

export function provenanceHref(ref: string) {
  if (isUserProvenanceRef(ref)) {
    return `/users?edit=${encodeURIComponent(ref)}`
  }
  if (isJobRunProvenanceRef(ref)) {
    return `/job-runs/${ref}`
  }
  return null
}

type ProvenanceLabelOptions = {
  users?: User[]
  jobRunTypes?: Record<string, JobRunType>
}

export function provenanceLabel(
  ref: string,
  options: ProvenanceLabelOptions = {}
) {
  if (isUserProvenanceRef(ref)) {
    const user = options.users?.find((entry) => entry.id === ref)
    return user?.email ?? ref
  }

  if (isJobRunProvenanceRef(ref)) {
    const jobType = options.jobRunTypes?.[ref]
    if (jobType) {
      return formatJobRunType(jobType)
    }
    return ref
  }

  return ref
}
