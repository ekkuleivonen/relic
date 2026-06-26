import { Link } from "react-router"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  formatJobRunType,
} from "@/features/job-runs/components/job-run-format"
import { JobRunStateBadge } from "@/features/job-runs/components/job-run-state-badge"
import type { JobRun, JobRunState, JobRunType } from "@/types/job-runs"

type JobRunChainCardProps = {
  parent: JobRun
  children: JobRun[]
}

type ChildGroup = {
  type: JobRunType
  label: string
  plannedCountKey: string
  objectResultKey: string
}

const childGroups: ChildGroup[] = [
  {
    type: "import_objects",
    label: "Imports",
    plannedCountKey: "import_objects_count",
    objectResultKey: "objects_imported",
  },
  {
    type: "refresh_objects",
    label: "Refreshes",
    plannedCountKey: "refresh_objects_count",
    objectResultKey: "objects_refreshed",
  },
  {
    type: "remove_objects",
    label: "Removals",
    plannedCountKey: "remove_objects_count",
    objectResultKey: "objects_deleted",
  },
]

export function JobRunChainCard({ parent, children }: JobRunChainCardProps) {
  const startedAt = chainStartedAt(parent, children)
  const finishedAt = chainFinishedAt(parent, children)
  const activeChildren = children.some(isActiveJobRun)
  const chainDone = parent.finished_at && !activeChildren
  const failures = children.filter((child) => child.state === "failed")

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Sync Chain</CardTitle>
            <CardDescription>
              Child jobs created by this sync run and their catalog mutations.
            </CardDescription>
          </div>
          <JobRunStateBadge state={chainState(parent, children)} />
        </div>
      </CardHeader>
      <CardContent className="grid gap-6">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <SummaryStat
            label="Objects seen"
            value={formatPayloadNumber(parent.result.objects_seen)}
          />
          <SummaryStat
            label="Child jobs"
            value={`${children.length}${chainDone ? "" : " active"}`}
          />
          <SummaryStat
            label="Duration"
            value={formatDuration(startedAt, finishedAt)}
          />
          <SummaryStat label="Failures" value={String(failures.length)} />
        </div>

        <div className="grid gap-3">
          {childGroups.map((group) => (
            <ChildJobGroup
              key={group.type}
              group={group}
              parent={parent}
              children={children.filter((child) => child.type === group.type)}
            />
          ))}
        </div>

        {failures.length > 0 && (
          <div className="grid gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
            <div className="text-sm font-medium">Failures</div>
            {failures.map((child) => (
              <div key={child.id} className="grid gap-1 text-sm">
                <Link
                  to={`/job-runs/${child.id}`}
                  className="font-mono text-xs underline-offset-4 hover:underline"
                >
                  {child.id}
                </Link>
                <div className="text-muted-foreground">
                  {child.error_message || "No error message recorded."}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function ChildJobGroup({
  group,
  parent,
  children,
}: {
  group: ChildGroup
  parent: JobRun
  children: JobRun[]
}) {
  const plannedCount = formatPayloadNumber(parent.result[group.plannedCountKey])
  const objectCount = children.reduce(
    (sum, child) => sum + numberPayloadValue(child.result[group.objectResultKey]),
    0
  )

  return (
    <div className="rounded-lg border bg-background/60 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="font-medium">{group.label}</div>
          <div className="mt-1 text-sm text-muted-foreground">
            {plannedCount} planned, {objectCount} completed across{" "}
            {children.length} job {children.length === 1 ? "run" : "runs"}
          </div>
        </div>
        <JobRunStateBadge state={groupState(children)} />
      </div>

      {children.length > 0 && (
        <div className="mt-4 grid gap-2">
          {children.map((child) => (
            <div
              key={child.id}
              className="flex flex-col gap-2 rounded-md border bg-card p-3 sm:flex-row sm:items-center sm:justify-between"
            >
              <div>
                <div className="text-sm font-medium">
                  {formatJobRunType(child.type)}
                </div>
                <div className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                  {child.id}
                </div>
                {child.error_message && (
                  <div className="mt-1 text-xs text-destructive">
                    {child.error_message}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-3">
                <JobRunStateBadge state={child.state} />
                <span className="text-xs text-muted-foreground">
                  {formatDuration(optionalDate(child.started_at), optionalDate(child.finished_at))}
                </span>
                <Button variant="ghost" size="sm" asChild>
                  <Link to={`/job-runs/${child.id}`}>View</Link>
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border bg-background/60 p-4">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  )
}

function chainState(parent: JobRun, children: JobRun[]): JobRunState {
  if (parent.state === "failed" || children.some((child) => child.state === "failed")) {
    return "failed"
  }
  if (parent.state === "cancelled" || children.some((child) => child.state === "cancelled")) {
    return "cancelled"
  }
  if (parent.state === "pending" || parent.state === "running" || children.some(isActiveJobRun)) {
    return "running"
  }
  return "succeeded"
}

function groupState(children: JobRun[]): JobRunState {
  if (children.length === 0) {
    return "succeeded"
  }
  if (children.some((child) => child.state === "failed")) {
    return "failed"
  }
  if (children.some((child) => child.state === "cancelled")) {
    return "cancelled"
  }
  if (children.some(isActiveJobRun)) {
    return "running"
  }
  return "succeeded"
}

function chainStartedAt(parent: JobRun, children: JobRun[]) {
  return earliestDate([
    optionalDate(parent.started_at),
    ...children.map((child) => optionalDate(child.started_at)),
  ])
}

function chainFinishedAt(parent: JobRun, children: JobRun[]) {
  if (!parent.finished_at || children.some(isActiveJobRun)) {
    return undefined
  }

  return latestDate([
    optionalDate(parent.finished_at),
    ...children.map((child) => optionalDate(child.finished_at)),
  ])
}

function earliestDate(dates: Array<Date | undefined>) {
  return dates
    .filter((date): date is Date => Boolean(date))
    .sort((left, right) => left.getTime() - right.getTime())[0]
}

function latestDate(dates: Array<Date | undefined>) {
  return dates
    .filter((date): date is Date => Boolean(date))
    .sort((left, right) => right.getTime() - left.getTime())[0]
}

function optionalDate(value: string | undefined) {
  return value ? new Date(value) : undefined
}

function formatDuration(startedAt: Date | undefined, finishedAt: Date | undefined) {
  if (!startedAt) {
    return "-"
  }

  const end = finishedAt ?? new Date()
  const seconds = Math.max(0, Math.round((end.getTime() - startedAt.getTime()) / 1000))
  if (seconds < 60) {
    return `${seconds}s`
  }

  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}m ${remainingSeconds}s`
}

function formatPayloadNumber(value: unknown) {
  if (typeof value === "number") {
    return String(value)
  }
  if (typeof value === "string" && value !== "") {
    return value
  }

  return "0"
}

function numberPayloadValue(value: unknown) {
  if (typeof value === "number") {
    return value
  }
  if (typeof value === "string") {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : 0
  }

  return 0
}

function isActiveJobRun(jobRun: JobRun) {
  return jobRun.state === "pending" || jobRun.state === "running"
}
