import { Link, useParams } from "react-router"
import { Loader2Icon } from "lucide-react"
import { useMemo, type ReactNode } from "react"

import { PageShell } from "@/components/page-shell"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useBucket } from "@/features/buckets/hooks/use-buckets"
import { ProvenanceReferenceLink } from "@/features/objects/components/provenance-reference-link"
import { UserAttributesCard } from "@/features/objects/components/user-attributes-card"
import {
  provenanceJobRunIds,
  useProvenanceJobRunTypes,
} from "@/features/objects/hooks/use-provenance-job-runs"
import { useObject } from "@/features/objects/hooks/use-objects"
import { useSession } from "@/hooks/use-session"
import { useUsers } from "@/hooks/use-users"
import type { User } from "@/types/auth"

export function ObjectDetailPage() {
  const { objectId } = useParams()
  const objectQuery = useObject(objectId)
  const object = objectQuery.data
  const bucketQuery = useBucket(object?.bucket_id)
  const bucket = bucketQuery.data
  const sessionQuery = useSession()
  const isAdmin = sessionQuery.data?.user.role === "admin"
  const usersQuery = useUsers({ enabled: isAdmin })

  return (
    <PageShell maxWidth="5xl">
      {objectQuery.isLoading && (
          <Card className="mt-6">
            <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin" />
              Loading object...
            </CardContent>
          </Card>
        )}

        {objectQuery.isError && (
          <Card className="mt-6">
            <CardHeader>
              <CardTitle>Could not load object</CardTitle>
              <CardDescription>
                The object may have been removed, or the API server may be
                unavailable.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={() => void objectQuery.refetch()}>
                Retry
              </Button>
            </CardContent>
          </Card>
        )}

        {object && (
          <div className="mt-6 grid gap-6">
            <header>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-3">
                    <h1 className="break-all text-2xl font-semibold tracking-tight">
                      {object.key}
                    </h1>
                    {object.attributes.upstream?.header?.content_type && (
                      <Badge variant="outline">
                        {object.attributes.upstream.header.content_type}
                      </Badge>
                    )}
                  </div>
                  <p className="mt-2 break-all text-sm text-muted-foreground">
                    {object.id}
                  </p>
                </div>
              </div>
            </header>

            <Card>
              <CardHeader>
                <CardTitle>Location</CardTitle>
                <CardDescription>
                  The catalog bucket and upstream key for this object.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <Detail
                  label="Bucket"
                  value={
                    bucket ? (
                      <Link
                        className="underline-offset-4 hover:underline"
                        to={`/buckets/${bucket.id}`}
                      >
                        {bucket.name}
                      </Link>
                    ) : (
                      object.bucket_id
                    )
                  }
                />
                <Detail label="Bucket ID" value={object.bucket_id} />
                {bucket && (
                  <Detail
                    label="Upstream bucket"
                    value={`${bucket.bucket_name}${bucket.prefix ? `/${bucket.prefix}` : ""}`}
                  />
                )}
                <Detail label="Key" value={object.key} />
                <Detail
                  label="Version ID"
                  value={mono(object.attributes.upstream?.s3?.version_id) || "-"}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Timestamps</CardTitle>
                <CardDescription>
                  Catalog lifecycle timestamps for sync inspection.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <Detail label="First seen" value={formatDate(object.first_seen_at)} />
                <Detail label="Last seen" value={formatDate(object.last_seen_at)} />
                <Detail label="Created" value={formatDate(object.created_at)} />
                <Detail label="Updated" value={formatDate(object.updated_at)} />
                <Detail
                  label="Upstream modified"
                  value={formatOptionalDate(
                    object.attributes.upstream?.last_modified
                  )}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Upstream metadata</CardTitle>
                <CardDescription>
                  Key attributes captured from listing and HEAD enrichment.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <Detail label="ETag" value={mono(object.attributes.upstream?.etag)} />
                <Detail
                  label="Size"
                  value={formatSize(object.attributes.upstream?.size)}
                />
                <Detail
                  label="Storage class"
                  value={storageClass(object.attributes.upstream)}
                />
                <Detail
                  label="Content type"
                  value={object.attributes.upstream?.header?.content_type ?? "-"}
                />
                <Detail
                  label="Cache control"
                  value={object.attributes.upstream?.header?.cache_control ?? "-"}
                />
                <Detail
                  label="Accept ranges"
                  value={object.attributes.upstream?.header?.accept_ranges ?? "-"}
                />
              </CardContent>
            </Card>

            <UserAttributesCard
              objectId={object.id}
              userAttributes={object.attributes.user}
              isAdmin={isAdmin}
            />

            <ProvenanceCard
              provenance={object.attribute_provenance}
              users={usersQuery.data}
              canLinkToUser={isAdmin}
            />

            <JsonCard
              title="Attributes"
              description="Full raw attributes JSON for comparing sync and HEAD enrichment output."
              value={object.attributes}
            />
          </div>
        )}
    </PageShell>
  )
}

function ProvenanceCard({
  provenance,
  users,
  canLinkToUser,
}: {
  provenance: Record<string, string>
  users: User[] | undefined
  canLinkToUser: boolean
}) {
  const entries = Object.entries(provenance)
  const jobRunIds = useMemo(() => provenanceJobRunIds(provenance), [provenance])
  const jobRunTypes = useProvenanceJobRunTypes(jobRunIds)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Attribute provenance</CardTitle>
        <CardDescription>
          The user or job run that last wrote each attribute path.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No provenance has been recorded for this object yet.
          </p>
        ) : (
          <div className="grid gap-3">
            {entries.map(([path, reference]) => (
              <div
                key={path}
                className="flex flex-col gap-1 rounded-lg border bg-background/60 p-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <div className="text-xs font-medium text-muted-foreground">
                    Attribute path
                  </div>
                  <div className="mt-1 font-mono text-sm">{path}</div>
                </div>
                <ProvenanceReferenceLink
                  reference={reference}
                  users={users}
                  jobRunTypes={jobRunTypes}
                  canLinkToUser={canLinkToUser}
                />
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function Detail({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-sm">{value}</div>
    </div>
  )
}

function JsonCard({
  title,
  description,
  value,
}: {
  title: string
  description: string
  value: unknown
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <pre className="max-h-[32rem] overflow-auto rounded-lg border bg-muted p-4 text-xs leading-relaxed">
          {JSON.stringify(value, null, 2)}
        </pre>
      </CardContent>
    </Card>
  )
}

function mono(value: string | undefined) {
  if (!value) {
    return <span className="text-muted-foreground">-</span>
  }

  return <span className="font-mono text-[11px]">{value}</span>
}

function formatSize(value: number | undefined) {
  if (value === undefined) {
    return <span className="text-muted-foreground">-</span>
  }

  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 1,
    notation: value >= 1024 * 1024 * 1024 ? "compact" : "standard",
    style: "unit",
    unit: "byte",
    unitDisplay: "narrow",
  }).format(value)
}

function storageClass(upstream: Record<string, unknown> | undefined) {
  if (!upstream) {
    return <span className="text-muted-foreground">-</span>
  }

  const s3 = upstream.s3
  if (isRecord(s3) && typeof s3.storage_class === "string") {
    return s3.storage_class
  }

  return <span className="text-muted-foreground">-</span>
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

function formatOptionalDate(value: string | undefined) {
  if (!value) {
    return <span className="text-muted-foreground">-</span>
  }

  return formatDate(value)
}
