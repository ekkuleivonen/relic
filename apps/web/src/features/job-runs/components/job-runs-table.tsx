import { Link } from "react-router"

import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  formatDate,
  formatJobRunType,
} from "@/features/job-runs/components/job-run-format"
import { JobRunProgress } from "@/features/job-runs/components/job-run-progress"
import { JobRunStateBadge } from "@/features/job-runs/components/job-run-state-badge"
import { JobRunTarget } from "@/features/job-runs/components/job-run-target"
import type { JobRun } from "@/types/job-runs"

type JobRunsTableProps = {
  jobRuns: JobRun[]
}

export function JobRunsTable({ jobRuns }: JobRunsTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Run</TableHead>
            <TableHead>State</TableHead>
            <TableHead>Target</TableHead>
            <TableHead>Progress</TableHead>
            <TableHead>Attempts</TableHead>
            <TableHead>Updated</TableHead>
            <TableHead className="w-24 text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobRuns.map((jobRun) => (
            <TableRow key={jobRun.id}>
              <TableCell>
                <div className="font-medium">{formatJobRunType(jobRun.type)}</div>
                <div className="mt-0.5 max-w-64 truncate font-mono text-[11px] text-muted-foreground">
                  {jobRun.id}
                </div>
              </TableCell>
              <TableCell>
                <JobRunStateBadge state={jobRun.state} />
              </TableCell>
              <TableCell>
                <JobRunTarget jobRun={jobRun} />
              </TableCell>
              <TableCell>
                <div className="max-w-64 truncate">
                  {jobRun.error_message || <JobRunProgress jobRun={jobRun} />}
                </div>
              </TableCell>
              <TableCell>
                {jobRun.attempt}/{jobRun.max_attempts}
              </TableCell>
              <TableCell>{formatDate(jobRun.updated_at)}</TableCell>
              <TableCell>
                <div className="flex justify-end">
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={`/job-runs/${jobRun.id}`}>View</Link>
                  </Button>
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
