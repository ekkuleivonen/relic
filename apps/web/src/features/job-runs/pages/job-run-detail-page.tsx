import { useParams } from "react-router"
import { Loader2Icon } from "lucide-react"

import { PageShell } from "@/components/page-shell"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { JobRunChainCard } from "@/features/job-runs/components/job-run-chain-card"
import { JobRunDetailCard } from "@/features/job-runs/components/job-run-detail-card"
import { useJobRun, useJobRuns } from "@/features/job-runs/hooks/use-job-runs"
import { JobRunObjectsCard } from "@/features/observability/components/job-run-objects-card"
import type { JobRun } from "@/types/job-runs"

export function JobRunDetailPage() {
  const { jobRunId } = useParams()
  const jobRunQuery = useJobRun(jobRunId)
  const jobRun = jobRunQuery.data
  const childRunsQuery = useJobRuns(
    {
      requestedByType: "job",
      requestedById: jobRun?.id,
      limit: 500,
    },
    {
      enabled: jobRun?.type === "sync_bucket",
    }
  )

  return (
    <PageShell>
      <section>
        {jobRunQuery.isLoading && (
            <Card>
              <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
                <Loader2Icon className="size-4 animate-spin" />
                Loading job run...
              </CardContent>
            </Card>
          )}

          {jobRunQuery.isError && (
            <Card>
              <CardHeader>
                <CardTitle>Could not load job run</CardTitle>
                <CardDescription>
                  The job run may have been deleted, or the API server may be
                  unavailable.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button
                  variant="outline"
                  onClick={() => void jobRunQuery.refetch()}
                >
                  Retry
                </Button>
              </CardContent>
            </Card>
          )}

          {jobRun && (
            <div className="grid gap-6">
              <JobRunDetailCard jobRun={jobRun} />
              {isObjectSyncJobRun(jobRun.type) && (
                <JobRunObjectsCard jobRun={jobRun} />
              )}
              {jobRun.type === "sync_bucket" && (
                <SyncChainSection
                  jobRun={jobRun}
                  isLoading={childRunsQuery.isLoading}
                  isError={childRunsQuery.isError}
                  onRetry={() => void childRunsQuery.refetch()}
                  childRuns={childRunsQuery.data?.job_runs ?? []}
                />
              )}
            </div>
          )}
        </section>
    </PageShell>
  )
}

function SyncChainSection({
  jobRun,
  isLoading,
  isError,
  onRetry,
  childRuns,
}: {
  jobRun: JobRun
  isLoading: boolean
  isError: boolean
  onRetry: () => void
  childRuns: JobRun[]
}) {
  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
          <Loader2Icon className="size-4 animate-spin" />
          Loading sync chain...
        </CardContent>
      </Card>
    )
  }

  if (isError) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Could not load sync chain</CardTitle>
          <CardDescription>
            The parent job loaded, but child job runs could not be fetched.
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

  return <JobRunChainCard parent={jobRun} children={childRuns} />
}

function isObjectSyncJobRun(type: JobRun["type"]) {
  return (
    type === "import_objects" ||
    type === "remove_objects" ||
    type === "refresh_objects"
  )
}
