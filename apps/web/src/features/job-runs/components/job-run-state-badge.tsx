import { Badge } from "@/components/ui/badge"
import type { JobRunState } from "@/types/job-runs"

type JobRunStateBadgeProps = {
  state: JobRunState
}

export function JobRunStateBadge({ state }: JobRunStateBadgeProps) {
  const variant = state === "failed" ? "destructive" : "outline"

  return <Badge variant={variant}>{formatJobRunState(state)}</Badge>
}

function formatJobRunState(state: JobRunState) {
  return state.charAt(0).toUpperCase() + state.slice(1)
}
