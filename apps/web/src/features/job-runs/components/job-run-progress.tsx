import { formatProgressText } from "@/features/job-runs/components/job-run-format"
import type { JobRun } from "@/types/job-runs"

type JobRunProgressProps = {
  jobRun: JobRun
}

export function JobRunProgress({ jobRun }: JobRunProgressProps) {
  const progress = formatProgressText(jobRun)

  if (progress === "-") {
    return <span className="text-muted-foreground">-</span>
  }

  return progress
}
