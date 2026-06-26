import { Loader2Icon, RefreshCwIcon } from "lucide-react"
import * as React from "react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { ObjectsTable } from "@/features/objects/components/objects-table"
import { useObjects } from "@/features/objects/hooks/use-objects"

type ObjectsCardProps = {
  bucketId?: string
  prefix?: string
}

export function ObjectsCard({ bucketId, prefix }: ObjectsCardProps) {
  const [keyContains, setKeyContains] = React.useState("")
  const objectsQuery = useObjects({
    bucketId,
    prefix,
    keyContains,
    limit: 100,
  })
  const objects = objectsQuery.data?.objects ?? []

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <CardTitle>Objects</CardTitle>
            <CardDescription>
              Browse active catalog rows from synced upstream buckets.
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void objectsQuery.refetch()}
            disabled={objectsQuery.isFetching}
          >
            {objectsQuery.isFetching ? (
              <Loader2Icon className="animate-spin" />
            ) : (
              <RefreshCwIcon />
            )}
            Refresh
          </Button>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4">
        <div className="max-w-sm">
          <Input
            value={keyContains}
            onChange={(event) => setKeyContains(event.target.value)}
            placeholder="Search object keys..."
          />
        </div>

        {objectsQuery.isLoading && (
          <div className="flex items-center gap-3 rounded-lg border px-4 py-6 text-sm text-muted-foreground">
            <Loader2Icon className="size-4 animate-spin" />
            Loading objects...
          </div>
        )}

        {objectsQuery.isError && (
          <div className="rounded-lg border px-4 py-6">
            <div className="font-medium">Could not load objects</div>
            <p className="mt-1 text-sm text-muted-foreground">
              Check that the API server is running, then retry the request.
            </p>
            <Button
              className="mt-4"
              variant="outline"
              onClick={() => void objectsQuery.refetch()}
            >
              Retry
            </Button>
          </div>
        )}

        {objectsQuery.isSuccess && objects.length === 0 && (
          <div className="rounded-lg border border-dashed px-4 py-8 text-center">
            <div className="font-medium">No objects found</div>
            <p className="mt-1 text-sm text-muted-foreground">
              Run a sync or adjust the key search to see cataloged objects.
            </p>
          </div>
        )}

        {objects.length > 0 && <ObjectsTable objects={objects} />}
      </CardContent>
    </Card>
  )
}
