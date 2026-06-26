import { Link, useParams } from "react-router"
import { ArrowLeftIcon, Loader2Icon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { JobRunDetailCard } from "@/features/job-runs/components/job-run-detail-card"
import { useJobRun } from "@/features/job-runs/hooks/use-job-runs"

export function JobRunDetailPage() {
  const { jobRunId } = useParams()
  const jobRunQuery = useJobRun(jobRunId)
  const jobRun = jobRunQuery.data

  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto w-full max-w-7xl px-6 py-8 lg:px-8">
        <Button variant="ghost" asChild>
          <Link to="/job-runs">
            <ArrowLeftIcon />
            Back to job runs
          </Link>
        </Button>

        <section className="mt-6">
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

          {jobRun && <JobRunDetailCard jobRun={jobRun} />}
        </section>
      </div>
    </main>
  )
}
