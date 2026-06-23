import { Link, useParams } from "react-router"
import { ArrowLeftIcon, Loader2Icon } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { EditBucketDialog } from "@/features/buckets/components/edit-bucket-dialog"
import { useBucket } from "@/features/buckets/hooks/use-buckets"

export function BucketDetailPage() {
  const { bucketId } = useParams()
  const bucketQuery = useBucket(bucketId)
  const bucket = bucketQuery.data

  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto w-full max-w-5xl px-6 py-8 lg:px-8">
        <Button variant="ghost" asChild>
          <Link to="/buckets">
            <ArrowLeftIcon />
            Back to buckets
          </Link>
        </Button>

        {bucketQuery.isLoading && (
          <Card className="mt-6">
            <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin" />
              Loading bucket...
            </CardContent>
          </Card>
        )}

        {bucketQuery.isError && (
          <Card className="mt-6">
            <CardHeader>
              <CardTitle>Could not load bucket</CardTitle>
              <CardDescription>
                The bucket may have been deleted, or the API server may be
                unavailable.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={() => void bucketQuery.refetch()}>
                Retry
              </Button>
            </CardContent>
          </Card>
        )}

        {bucket && (
          <div className="mt-6 grid gap-6">
            <header>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="flex items-center gap-3">
                    <h1 className="text-2xl font-semibold tracking-tight">
                      {bucket.name}
                    </h1>
                    <Badge variant="outline">{bucket.provider}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {bucket.bucket_name}
                    {bucket.prefix ? `/${bucket.prefix}` : ""}
                  </p>
                </div>
                <EditBucketDialog bucket={bucket} />
              </div>
            </header>

            <Card>
              <CardHeader>
                <CardTitle>Connection</CardTitle>
                <CardDescription>
                  Credentials are encrypted by the API and are not returned to
                  the browser.
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <Detail label="Endpoint URL" value={bucket.endpoint_url} />
                <Detail label="Region" value={bucket.region} />
                <Detail label="Bucket name" value={bucket.bucket_name} />
                <Detail
                  label="Prefix"
                  value={bucket.prefix || "All objects"}
                />
                <Detail label="Created" value={formatDate(bucket.created_at)} />
                <Detail label="Updated" value={formatDate(bucket.updated_at)} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Next actions</CardTitle>
                <CardDescription>
                  Import controls and job status will live here once the import
                  endpoint is ready.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button disabled>Run import</Button>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </main>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 break-words text-sm">{value}</div>
    </div>
  )
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}
