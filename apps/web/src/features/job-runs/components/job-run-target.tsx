import type { JobRun } from "@/types/job-runs"

type JobRunTargetProps = {
  jobRun: JobRun
}

export function JobRunTarget({ jobRun }: JobRunTargetProps) {
  if (!jobRun.target_type && !jobRun.target_id) {
    return <span className="text-muted-foreground">-</span>
  }

  return (
    <div>
      <div>{jobRun.target_type || "Unknown"}</div>
      {jobRun.target_id && (
        <div className="mt-0.5 max-w-48 truncate font-mono text-[11px] text-muted-foreground">
          {jobRun.target_id}
        </div>
      )}
    </div>
  )
}
