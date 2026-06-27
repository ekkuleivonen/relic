import { Loader2Icon, RefreshCwIcon } from "lucide-react"

import { PageShell } from "@/components/page-shell"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { JobRunsTable } from "@/features/job-runs/components/job-runs-table"
import { useJobRuns } from "@/features/job-runs/hooks/use-job-runs"

export function JobRunsPage() {
  const jobRunsQuery = useJobRuns({ limit: 100 })
  const jobRuns = jobRunsQuery.data?.job_runs ?? []

  return (
    <PageShell>
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Job runs</h1>
          <p className="mt-4 max-w-2xl text-sm/7 text-muted-foreground">
            Inspect recent background work, progress updates, failures, and
            retry attempts.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => void jobRunsQuery.refetch()}
          disabled={jobRunsQuery.isFetching}
        >
          {jobRunsQuery.isFetching ? (
            <Loader2Icon className="animate-spin" />
          ) : (
            <RefreshCwIcon />
          )}
          Refresh
        </Button>
      </header>

      <section className="mt-8">
        {jobRunsQuery.isLoading && <LoadingState />}
        {jobRunsQuery.isError && (
          <ErrorState onRetry={() => void jobRunsQuery.refetch()} />
        )}
        {jobRunsQuery.isSuccess && jobRuns.length === 0 && <EmptyState />}
        {jobRuns.length > 0 && <JobRunsTable jobRuns={jobRuns} />}
      </section>
    </PageShell>
  )
}

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
        <Loader2Icon className="size-4 animate-spin" />
        Loading job runs...
      </CardContent>
    </Card>
  )
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Could not load job runs</CardTitle>
        <CardDescription>
          Check that the API server is running, then retry the request.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button variant="outline" onClick={onRetry}>
          Retry
        </Button>
      </CardContent>
    </Card>
  )
}

function EmptyState() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>No job runs yet</CardTitle>
        <CardDescription>
          Queue a bucket sync to create the first job run.
        </CardDescription>
      </CardHeader>
    </Card>
  )
}
