import { Link, useParams } from "react-router"
import { ArrowLeftIcon, Loader2Icon } from "lucide-react"
import type { ReactNode } from "react"

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
import { useObject } from "@/features/objects/hooks/use-objects"

export function ObjectDetailPage() {
  const { objectId } = useParams()
  const objectQuery = useObject(objectId)
  const object = objectQuery.data
  const bucketQuery = useBucket(object?.bucket_id)
  const bucket = bucketQuery.data

  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto w-full max-w-5xl px-6 py-8 lg:px-8">
        <Button variant="ghost" asChild>
          <Link to="/objects">
            <ArrowLeftIcon />
            Back to objects
          </Link>
        </Button>

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
                <Detail label="Version ID" value={object.version_id || "-"} />
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

            <JsonCard
              title="Attribute provenance"
              description="Where each object attribute came from during catalog enrichment."
              value={object.attribute_provenance}
            />

            <JsonCard
              title="Attributes"
              description="Full raw attributes JSON for comparing sync and HEAD enrichment output."
              value={object.attributes}
            />
          </div>
        )}
      </div>
    </main>
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
