import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { formatOptionalDate } from "@/features/job-runs/components/job-run-format"
import { BucketEventStateBadge } from "@/features/observability/components/bucket-event-state-badge"
import type { BucketEvent } from "@/types/bucket-events"

type BucketEventDetailCardProps = {
  event: BucketEvent
  bucketName?: string
}

export function BucketEventDetailCard({
  event,
  bucketName,
}: BucketEventDetailCardProps) {
  return (
    <div className="grid gap-6">
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <CardTitle>{event.event_name}</CardTitle>
              <CardDescription className="font-mono">{event.id}</CardDescription>
            </div>
            <BucketEventStateBadge state={event.state} />
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <Detail label="Bucket" value={bucketName ?? event.bucket_id} />
          <Detail label="Object key" value={event.object_key || "-"} />
          <Detail label="Transport" value={event.transport} />
          <Detail label="Event time" value={formatOptionalDate(event.event_time)} />
          <Detail label="Received" value={formatOptionalDate(event.received_at)} />
          <Detail label="Processed" value={formatOptionalDate(event.processed_at)} />
        </CardContent>
      </Card>

      {event.error_message && (
        <Card>
          <CardHeader>
            <CardTitle>Error</CardTitle>
            <CardDescription>
              Processing failed for this bucket event.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="overflow-auto rounded-lg border bg-muted p-4 text-xs whitespace-pre-wrap">
              {event.error_message}
            </pre>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Envelope</CardTitle>
          <CardDescription>
            Raw upstream notification payload stored by Pithosys.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="overflow-auto rounded-lg border bg-muted p-4 text-xs whitespace-pre-wrap">
            {JSON.stringify(event.envelope, null, 2)}
          </pre>
        </CardContent>
      </Card>
    </div>
  )
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm break-all">{value}</div>
    </div>
  )
}
