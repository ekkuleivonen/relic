import { Link, useParams } from "react-router"
import { Loader2Icon } from "lucide-react"

import { PageShell } from "@/components/page-shell"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useBucket } from "@/features/buckets/hooks/use-buckets"
import { BucketEventDetailCard } from "@/features/observability/components/bucket-event-detail-card"
import { useBucketEvent } from "@/features/observability/hooks/use-bucket-events"

export function BucketEventDetailPage() {
  const { eventId } = useParams()
  const eventQuery = useBucketEvent(eventId)
  const event = eventQuery.data
  const bucketQuery = useBucket(event?.bucket_id)

  return (
    <PageShell>
      <section>
        {eventQuery.isLoading && (
          <Card>
            <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
              <Loader2Icon className="size-4 animate-spin" />
              Loading bucket event...
            </CardContent>
          </Card>
        )}

        {eventQuery.isError && (
          <Card>
            <CardHeader>
              <CardTitle>Could not load bucket event</CardTitle>
              <CardDescription>
                The event may have been deleted, or the API server may be
                unavailable.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" onClick={() => void eventQuery.refetch()}>
                Retry
              </Button>
            </CardContent>
          </Card>
        )}

        {event && (
          <div className="grid gap-6">
            <BucketEventDetailCard
              event={event}
              bucketName={bucketQuery.data?.name}
            />
            <Card>
              <CardHeader>
                <CardTitle>Related object sync</CardTitle>
                <CardDescription>
                  Object sync runs triggered from bucket events for this bucket
                  are listed on the object sync page.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button variant="outline" asChild>
                  <Link
                    to={`/object-sync?bucket=${encodeURIComponent(event.bucket_id)}`}
                  >
                    View object sync for bucket
                  </Link>
                </Button>
              </CardContent>
            </Card>
          </div>
        )}
      </section>
    </PageShell>
  )
}
