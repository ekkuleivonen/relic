import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { JobRunTraceProgress } from "@/features/job-runs/components/job-run-trace-progress"
import { formatOptionalDate } from "@/features/job-runs/components/job-run-format"
import { useActiveBucketSync } from "@/features/buckets/hooks/use-active-bucket-sync"

type BucketSyncStatusCardProps = {
  bucketId: string
}

export function BucketSyncStatusCard({ bucketId }: BucketSyncStatusCardProps) {
  const syncQuery = useActiveBucketSync(bucketId)

  if (syncQuery.isLoading) {
    return null
  }

  if (syncQuery.isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Sync status</CardTitle>
          <CardDescription>Could not load the latest bucket sync.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" size="sm" onClick={() => void syncQuery.refetch()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  if (!syncQuery.hasSyncHistory || !syncQuery.jobRun || !syncQuery.traceSummary) {
    return null
  }

  const { jobRun, traceSummary, progressView, isActive } = syncQuery

  if (!isActive && !progressView?.isFailed && !progressView?.isComplete) {
    return null
  }

  if (!isActive && progressView?.isComplete) {
    return (
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Last sync</CardTitle>
          <CardDescription>
            Completed {formatOptionalDate(jobRun.finished_at)} ·{" "}
            {progressView.detailLine}
          </CardDescription>
        </CardHeader>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sync status</CardTitle>
        <CardDescription>
          {isActive
            ? "Reconciling this bucket with upstream object storage."
            : "The most recent sync run for this bucket."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <JobRunTraceProgress
          jobRun={jobRun}
          traceSummary={traceSummary}
          detailHref={`/job-runs/${jobRun.id}`}
        />
      </CardContent>
    </Card>
  )
}
