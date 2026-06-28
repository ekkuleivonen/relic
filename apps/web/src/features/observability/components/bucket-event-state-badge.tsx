import { Badge } from "@/components/ui/badge"
import type { BucketEventState } from "@/types/bucket-events"

type BucketEventStateBadgeProps = {
  state: BucketEventState
}

export function BucketEventStateBadge({ state }: BucketEventStateBadgeProps) {
  const variant =
    state === "failed" ? "destructive" : state === "pending" ? "outline" : "secondary"

  return <Badge variant={variant}>{formatBucketEventState(state)}</Badge>
}

function formatBucketEventState(state: BucketEventState) {
  return state.charAt(0).toUpperCase() + state.slice(1)
}
