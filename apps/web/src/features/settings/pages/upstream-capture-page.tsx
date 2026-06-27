import * as React from "react"
import { Loader2Icon, Settings2Icon } from "lucide-react"

import { PageShell } from "@/components/page-shell"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { CaptureFieldsTable } from "@/features/settings/components/capture-fields-table"
import { CreateCaptureFieldDialog } from "@/features/settings/components/create-capture-field-dialog"
import { useUpstreamCaptureFields } from "@/features/settings/hooks/use-upstream-capture-fields"
import type { UpstreamCaptureField } from "@/types/upstream-capture"

type OriginFilter = "all" | "platform" | "user"

export function UpstreamCapturePage() {
  const fieldsQuery = useUpstreamCaptureFields()
  const [originFilter, setOriginFilter] = React.useState<OriginFilter>("all")

  const fields = fieldsQuery.data ?? []
  const filteredFields = filterFields(fields, originFilter)
  const platformCount = fields.filter((field) => field.origin === "platform").length
  const userCount = fields.filter((field) => field.origin === "user").length
  const enabledCount = fields.filter((field) => field.enabled).length

  return (
    <PageShell maxWidth="6xl">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Upstream capture
          </h1>
          <p className="mt-4 max-w-3xl text-sm/7 text-muted-foreground">
            Control which S3 HEAD and tagging data Relic stores under{" "}
            <span className="font-mono">upstream.*</span> during import and
            refresh. Required fields stay enabled for sync and scan. Disabling a
            field stops future writes; existing object JSON is unchanged until
            re-import.
          </p>
        </div>
        <CreateCaptureFieldDialog />
      </header>

      <section className="mt-8 grid gap-4 sm:grid-cols-3">
        <SummaryCard label="Enabled fields" value={enabledCount} />
        <SummaryCard label="Platform fields" value={platformCount} />
        <SummaryCard label="Custom fields" value={userCount} />
      </section>

      <section className="mt-8">
        <div className="mb-4 flex flex-wrap gap-2">
          <FilterButton
            active={originFilter === "all"}
            onClick={() => setOriginFilter("all")}
          >
            All ({fields.length})
          </FilterButton>
          <FilterButton
            active={originFilter === "platform"}
            onClick={() => setOriginFilter("platform")}
          >
            Platform ({platformCount})
          </FilterButton>
          <FilterButton
            active={originFilter === "user"}
            onClick={() => setOriginFilter("user")}
          >
            Custom ({userCount})
          </FilterButton>
        </div>

        {fieldsQuery.isLoading && <LoadingState />}
        {fieldsQuery.isError && (
          <ErrorState onRetry={() => void fieldsQuery.refetch()} />
        )}
        {fieldsQuery.isSuccess && filteredFields.length === 0 && (
          <EmptyState originFilter={originFilter} />
        )}
        {fieldsQuery.isSuccess && filteredFields.length > 0 && (
          <CaptureFieldsTable fields={filteredFields} />
        )}
      </section>
    </PageShell>
  )
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-3xl tabular-nums">{value}</CardTitle>
      </CardHeader>
    </Card>
  )
}

function FilterButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={active ? "default" : "outline"}
      onClick={onClick}
    >
      {children}
    </Button>
  )
}

function filterFields(fields: UpstreamCaptureField[], originFilter: OriginFilter) {
  if (originFilter === "all") {
    return fields
  }

  return fields.filter((field) => field.origin === originFilter)
}

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
        <Loader2Icon className="size-4 animate-spin" />
        Loading capture fields...
      </CardContent>
    </Card>
  )
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Could not load capture fields</CardTitle>
        <CardDescription>
          Check that the API server is running, then retry the request.
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

function EmptyState({ originFilter }: { originFilter: OriginFilter }) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center px-6 py-14 text-center">
        <div className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Settings2Icon className="size-5" aria-hidden="true" />
        </div>
        <CardTitle className="mt-5">
          {originFilter === "user"
            ? "No custom capture fields yet"
            : "No capture fields match this filter"}
        </CardTitle>
        <CardDescription className="mt-2 max-w-md">
          {originFilter === "user"
            ? "Add a vendor header, metadata key, or tag mapping when you need data beyond the platform defaults."
            : "Try another filter or reload once platform fields have been seeded."}
        </CardDescription>
        {originFilter === "user" ? (
          <div className="mt-6">
            <CreateCaptureFieldDialog />
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
