import type { ReactNode } from "react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  formatJobRunType,
  formatOptionalDate,
} from "@/features/job-runs/components/job-run-format"
import { JobRunProgress } from "@/features/job-runs/components/job-run-progress"
import { JobRunStateBadge } from "@/features/job-runs/components/job-run-state-badge"
import { JobRunTarget } from "@/features/job-runs/components/job-run-target"
import type { JobRun, JobRunPayload } from "@/types/job-runs"

type JobRunDetailCardProps = {
  jobRun: JobRun
}

export function JobRunDetailCard({ jobRun }: JobRunDetailCardProps) {
  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle>{formatJobRunType(jobRun.type)}</CardTitle>
              <CardDescription className="font-mono">{jobRun.id}</CardDescription>
            </div>
            <JobRunStateBadge state={jobRun.state} />
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Detail label="Target" value={<JobRunTarget jobRun={jobRun} />} />
          <Detail
            label="Progress"
            value={
              <JobRunProgress
                jobRun={jobRun}
                traceSummary={jobRun.trace_summary}
              />
            }
          />
          <Detail label="Attempt" value={`${jobRun.attempt}/${jobRun.max_attempts}`} />
          <Detail label="Requested by" value={formatRequester(jobRun)} />
          <Detail label="Available" value={formatOptionalDate(jobRun.available_at)} />
          <Detail label="Started" value={formatOptionalDate(jobRun.started_at)} />
          <Detail label="Finished" value={formatOptionalDate(jobRun.finished_at)} />
          <Detail label="Updated" value={formatOptionalDate(jobRun.updated_at)} />
        </CardContent>
      </Card>

      {jobRun.error_message && (
        <Card>
          <CardHeader>
            <CardTitle>Error</CardTitle>
            <CardDescription>
              Last error message recorded for this job run.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="overflow-auto rounded-lg border bg-muted p-4 text-xs whitespace-pre-wrap">
              {jobRun.error_message}
            </pre>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <PayloadCard title="Input" payload={jobRun.input} />
        <PayloadCard title="Progress" payload={jobRun.progress} />
        <PayloadCard title="Result" payload={jobRun.result} />
      </div>
    </div>
  )
}

function Detail({
  label,
  value,
}: {
  label: string
  value: ReactNode
}) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-sm">{value}</div>
    </div>
  )
}

function PayloadCard({
  title,
  payload,
}: {
  title: string
  payload: JobRunPayload
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <pre className="overflow-auto rounded-lg border bg-muted p-4 text-xs">
          {JSON.stringify(payload, null, 2)}
        </pre>
      </CardContent>
    </Card>
  )
}

function formatRequester(jobRun: JobRun) {
  if (!jobRun.requested_by_type && !jobRun.requested_by_id) {
    return <span className="text-muted-foreground">-</span>
  }

  return [jobRun.requested_by_type, jobRun.requested_by_id]
    .filter(Boolean)
    .join(" / ")
}
