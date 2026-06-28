import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { objectKeysFromJobRun } from "@/features/observability/lib/job-run-objects"
import type { JobRun } from "@/types/job-runs"

type JobRunObjectsCardProps = {
  jobRun: JobRun
}

export function JobRunObjectsCard({ jobRun }: JobRunObjectsCardProps) {
  const keys = objectKeysFromJobRun(jobRun)
  const total = Array.isArray(jobRun.input.objects)
    ? jobRun.input.objects.length
    : keys.length

  if (total === 0) {
    return null
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Objects</CardTitle>
        <CardDescription>
          {total} object{total === 1 ? "" : "s"} in this run
          {keys.length < total ? ` (showing first ${keys.length})` : ""}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="grid gap-1 font-mono text-xs">
          {keys.map((key) => (
            <li key={key} className="truncate">
              {key}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}
