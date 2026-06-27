import { useQueries } from "@tanstack/react-query"
import { useMemo } from "react"

import { jobRunKeys } from "@/features/job-runs/hooks/use-job-runs"
import { isJobRunProvenanceRef } from "@/features/objects/lib/provenance-ref"
import { apiRequest } from "@/lib/api"
import type { JobRun } from "@/types/job-runs"

export function useProvenanceJobRunTypes(jobRunIds: string[]) {
  const queries = useQueries({
    queries: jobRunIds.map((id) => ({
      queryKey: jobRunKeys.detail(id),
      queryFn: () => apiRequest<JobRun>(`/job-runs/${id}`),
      staleTime: 60_000,
    })),
  })

  return useMemo(() => {
    const jobRunTypes: Record<string, JobRun["type"]> = {}

    for (const query of queries) {
      if (query.data) {
        jobRunTypes[query.data.id] = query.data.type
      }
    }

    return jobRunTypes
  }, [queries])
}

export function provenanceJobRunIds(provenance: Record<string, string>) {
  return [
    ...new Set(Object.values(provenance).filter((reference) => isJobRunProvenanceRef(reference))),
  ]
}
