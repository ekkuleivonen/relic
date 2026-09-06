import { Link, useNavigate, useParams } from "react-router"
import { Loader2Icon, RefreshCwIcon } from "lucide-react"

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
import { DeleteCollectionDialog } from "@/features/collections/components/delete-collection-dialog"
import { EditCollectionDialog } from "@/features/collections/components/edit-collection-dialog"
import {
  useCollection,
  useCollectionObjects,
} from "@/features/collections/hooks/use-collections"
import { ObjectsTable } from "@/features/objects/components/objects-table"
import { useSession } from "@/hooks/use-session"
import { extractApiError } from "@/lib/api"

export function CollectionDetailPage() {
  const { collectionId } = useParams()
  const navigate = useNavigate()
  const sessionQuery = useSession()
  const collectionQuery = useCollection(collectionId)
  const objectsQuery = useCollectionObjects(collectionId)
  const collection = collectionQuery.data
  const isAdmin = sessionQuery.data?.user.role === "admin"
  const objects = objectsQuery.data?.objects ?? []

  return (
    <PageShell maxWidth="5xl">
      {collectionQuery.isLoading && (
        <Card className="mt-6">
          <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
            <Loader2Icon className="size-4 animate-spin" />
            Loading collection...
          </CardContent>
        </Card>
      )}

      {collectionQuery.isError && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle>Could not load collection</CardTitle>
            <CardDescription>
              The collection may have been deleted, or the API server may be
              unavailable.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex gap-2">
            <Button variant="outline" onClick={() => void collectionQuery.refetch()}>
              Retry
            </Button>
            <Button variant="ghost" asChild>
              <Link to="/collections">Back to collections</Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {collection && (
        <div className="mt-6 grid gap-6">
          <header>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-semibold tracking-tight">
                    {collection.name}
                  </h1>
                  <Badge
                    variant={
                      collection.status === "valid" ? "outline" : "destructive"
                    }
                  >
                    {collection.status}
                  </Badge>
                </div>
                {collection.description ? (
                  <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
                    {collection.description}
                  </p>
                ) : null}
              </div>
              {isAdmin ? (
                <div className="flex gap-2">
                  <EditCollectionDialog collection={collection} />
                  <DeleteCollectionDialog
                    collection={collection}
                    onDeleted={() => navigate("/collections")}
                  />
                </div>
              ) : null}
            </div>
          </header>

          <Card>
            <CardHeader>
              <CardTitle>Saved query</CardTitle>
              <CardDescription>
                Membership is derived from this PithosysQL query.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <pre className="overflow-x-auto rounded-lg border bg-muted/30 p-4 font-mono text-sm leading-6">
                {collection.query}
              </pre>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <CardTitle>Matching objects</CardTitle>
                  <CardDescription>
                    Objects currently matching the saved query.
                  </CardDescription>
                </div>
                <Button
                  size="sm"
                  variant="outline"
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
              {objectsQuery.isLoading && (
                <div className="flex items-center gap-3 rounded-lg border px-4 py-6 text-sm text-muted-foreground">
                  <Loader2Icon className="size-4 animate-spin" />
                  Loading objects...
                </div>
              )}

              {objectsQuery.isError && (
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-6">
                  <div className="font-medium text-destructive">
                    Could not load collection objects
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {extractApiError(objectsQuery.error)}
                  </p>
                </div>
              )}

              {objectsQuery.isSuccess && objects.length === 0 && (
                <div className="rounded-lg border border-dashed px-4 py-8 text-center">
                  <div className="font-medium">No objects matched</div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Try syncing buckets or broadening the query.
                  </p>
                </div>
              )}

              {objects.length > 0 && <ObjectsTable objects={objects} />}
            </CardContent>
          </Card>
        </div>
      )}
    </PageShell>
  )
}
