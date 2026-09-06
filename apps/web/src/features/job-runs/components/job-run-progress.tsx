import {
  formatProgressText,
  formatTraceProgressLine,
} from "@/features/job-runs/components/job-run-format"
import type { JobRun, TraceSummary } from "@/types/job-runs"

type JobRunProgressProps = {
  jobRun: JobRun
  traceSummary?: TraceSummary
}

export function JobRunProgress({ jobRun, traceSummary }: JobRunProgressProps) {
  if (
    traceSummary &&
    (jobRun.type === "sync_bucket" || jobRun.type === "scan_bucket")
  ) {
    const line = formatTraceProgressLine(traceSummary, jobRun.type)
    if (line) {
      return line
    }
  }

  const progress = formatProgressText(jobRun)

  if (progress === "-") {
    return <span className="text-muted-foreground">-</span>
  }

  return progress
}
