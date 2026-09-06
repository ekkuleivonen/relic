import { Link, useNavigate, useParams } from "react-router"
import { Loader2Icon } from "lucide-react"

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
import { BucketSyncStatusCard } from "@/features/buckets/components/bucket-sync-status-card"
import { DeleteBucketDialog } from "@/features/buckets/components/delete-bucket-dialog"
import { EditBucketDialog } from "@/features/buckets/components/edit-bucket-dialog"
import { ScanBucketButton } from "@/features/buckets/components/scan-bucket-button"
import { SyncBucketButton } from "@/features/buckets/components/sync-bucket-button"
import { useActiveBucketSync } from "@/features/buckets/hooks/use-active-bucket-sync"
import { useBucket } from "@/features/buckets/hooks/use-buckets"
import { ObjectsCard } from "@/features/objects/components/objects-card"

export function BucketDetailPage() {
  const { bucketId } = useParams()
  const navigate = useNavigate()
  const bucketQuery = useBucket(bucketId)
  const bucket = bucketQuery.data
  const activeSync = useActiveBucketSync(bucket?.id)

  return (
    <PageShell maxWidth="5xl">
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
                    <Badge variant="outline">{bucket.upstream}</Badge>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {bucket.bucket_name}
                    {bucket.prefix ? `/${bucket.prefix}` : ""}
                  </p>
                </div>
                <div className="flex gap-2">
                  <EditBucketDialog bucket={bucket} />
                  <DeleteBucketDialog
                    bucket={bucket}
                    onDeleted={() => navigate("/buckets")}
                  />
                </div>
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
                <CardTitle>Scheduled scan</CardTitle>
                <CardDescription>
                  Background verification runs are configured globally for all
                  buckets.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  Manage scan enablement and interval under{" "}
                  <Link
                    to="/settings/jobs"
                    className="font-medium text-foreground underline-offset-4 hover:underline"
                  >
                    Settings → Jobs
                  </Link>
                  .
                </p>
              </CardContent>
            </Card>

            <BucketSyncStatusCard bucketId={bucket.id} />

            <ObjectsCard
              bucketId={bucket.id}
              prefix={bucket.prefix || undefined}
              syncInProgress={activeSync.isActive}
              syncDetailLine={activeSync.progressView?.detailLine}
            />

            <Card>
              <CardHeader>
                <CardTitle>Next actions</CardTitle>
                <CardDescription>
                  Queue a scan to sample catalog drift, or a full sync to
                  reconcile the active object catalog.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                <ScanBucketButton bucketId={bucket.id} />
                <SyncBucketButton bucketId={bucket.id} />
              </CardContent>
            </Card>
          </div>
        )}
    </PageShell>
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
