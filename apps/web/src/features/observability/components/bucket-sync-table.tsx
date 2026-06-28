import { Link } from "react-router"

import { Badge } from "@/components/ui/badge"
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
} from "@/features/job-runs/components/job-run-format"
import { JobRunProgress } from "@/features/job-runs/components/job-run-progress"
import { JobRunStateBadge } from "@/features/job-runs/components/job-run-state-badge"
import { JobRunTarget } from "@/features/job-runs/components/job-run-target"
import type { JobRun } from "@/types/job-runs"

type BucketSyncTableProps = {
  jobRuns: JobRun[]
}

export function BucketSyncTable({ jobRuns }: BucketSyncTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Kind</TableHead>
            <TableHead>State</TableHead>
            <TableHead>Target</TableHead>
            <TableHead>Progress</TableHead>
            <TableHead>Updated</TableHead>
            <TableHead className="w-24 text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {jobRuns.map((jobRun) => (
            <TableRow key={jobRun.id}>
              <TableCell>
                <BucketSyncKindBadge type={jobRun.type} />
                <div className="mt-1 max-w-64 truncate font-mono text-[11px] text-muted-foreground">
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

function BucketSyncKindBadge({ type }: { type: JobRun["type"] }) {
  const label = type === "scan_bucket" ? "Scan" : "Sync"

  return <Badge variant="outline">{label}</Badge>
}
