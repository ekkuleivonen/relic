import { ArchiveIcon, Loader2Icon } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { CreateBucketDialog } from "@/features/buckets/components/create-bucket-dialog"
import { BucketsTable } from "@/features/buckets/components/buckets-table"
import { useBuckets } from "@/features/buckets/hooks/use-buckets"

export function BucketsPage() {
  const bucketsQuery = useBuckets()
  const buckets = bucketsQuery.data?.buckets ?? []

  return (
    <main className="min-h-svh bg-background text-foreground">
      <div className="mx-auto w-full max-w-7xl px-6 py-8 lg:px-8">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <img src="/logo.svg" alt="" className="size-9 rounded-lg" />
              <div>
                <div className="text-xs text-muted-foreground">Relic admin</div>
                <h1 className="text-2xl font-semibold tracking-tight">
                  Buckets
                </h1>
              </div>
            </div>
            <p className="mt-4 max-w-2xl text-sm/7 text-muted-foreground">
              Connect S3-compatible buckets, store encrypted credentials, and
              prepare them for inventory imports.
            </p>
          </div>
          <CreateBucketDialog />
        </header>

        <section className="mt-8">
          {bucketsQuery.isLoading && <LoadingState />}
          {bucketsQuery.isError && (
            <ErrorState onRetry={() => void bucketsQuery.refetch()} />
          )}
          {bucketsQuery.isSuccess && buckets.length === 0 && <EmptyState />}
          {bucketsQuery.isSuccess && buckets.length > 0 && (
            <BucketsTable buckets={buckets} />
          )}
        </section>
      </div>
    </main>
  )
}

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
        <Loader2Icon className="size-4 animate-spin" />
        Loading buckets...
      </CardContent>
    </Card>
  )
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Could not load buckets</CardTitle>
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

function EmptyState() {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center px-6 py-14 text-center">
        <div className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <ArchiveIcon className="size-5" aria-hidden="true" />
        </div>
        <CardTitle className="mt-5">Connect your first bucket</CardTitle>
        <CardDescription className="mt-2 max-w-md">
          Relic starts by connecting to existing object storage. Add a bucket to
          make it available for import and cataloging.
        </CardDescription>
        <div className="mt-6">
          <CreateBucketDialog triggerLabel="Connect bucket" />
        </div>
      </CardContent>
    </Card>
  )
}
