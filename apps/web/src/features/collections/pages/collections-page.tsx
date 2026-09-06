import { LayersIcon, Loader2Icon } from "lucide-react"

import { PageShell } from "@/components/page-shell"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { CollectionsTable } from "@/features/collections/components/collections-table"
import { CreateCollectionDialog } from "@/features/collections/components/create-collection-dialog"
import { useCollections } from "@/features/collections/hooks/use-collections"
import { useSession } from "@/hooks/use-session"

export function CollectionsPage() {
  const sessionQuery = useSession()
  const collectionsQuery = useCollections()
  const collections = collectionsQuery.data?.collections ?? []
  const isAdmin = sessionQuery.data?.user.role === "admin"

  return (
    <PageShell>
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Collections</h1>
          <p className="mt-4 max-w-2xl text-sm/7 text-muted-foreground">
            Saved PithosysQL queries that stay up to date as your catalog changes.
            Collections are views, not folders.
          </p>
        </div>
        {isAdmin ? <CreateCollectionDialog /> : null}
      </header>

      <section className="mt-8">
        {collectionsQuery.isLoading && <LoadingState />}
        {collectionsQuery.isError && (
          <ErrorState onRetry={() => void collectionsQuery.refetch()} />
        )}
        {collectionsQuery.isSuccess && collections.length === 0 && (
          <EmptyState isAdmin={isAdmin} />
        )}
        {collectionsQuery.isSuccess && collections.length > 0 && (
          <CollectionsTable collections={collections} isAdmin={isAdmin} />
        )}
      </section>
    </PageShell>
  )
}

function LoadingState() {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 py-8 text-muted-foreground">
        <Loader2Icon className="size-4 animate-spin" />
        Loading collections...
      </CardContent>
    </Card>
  )
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Could not load collections</CardTitle>
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

function EmptyState({ isAdmin }: { isAdmin: boolean }) {
  return (
    <Card className="border-dashed">
      <CardContent className="flex flex-col items-center px-6 py-14 text-center">
        <div className="flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <LayersIcon className="size-6" />
        </div>
        <h2 className="mt-4 text-lg font-medium">No collections yet</h2>
        <p className="mt-2 max-w-md text-sm text-muted-foreground">
          {isAdmin
            ? "Create a collection from a PithosysQL query, or save one from the Objects search panel."
            : "An admin can create collections from saved PithosysQL queries."}
        </p>
        {isAdmin ? (
          <div className="mt-6">
            <CreateCollectionDialog triggerLabel="Create your first collection" />
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}
