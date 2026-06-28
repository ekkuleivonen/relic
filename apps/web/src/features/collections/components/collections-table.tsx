import { Link } from "react-router"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { DeleteCollectionDialog } from "@/features/collections/components/delete-collection-dialog"
import { EditCollectionDialog } from "@/features/collections/components/edit-collection-dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { Collection } from "@/types/collections"

type CollectionsTableProps = {
  collections: Collection[]
  isAdmin: boolean
}

export function CollectionsTable({
  collections,
  isAdmin,
}: CollectionsTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Description</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Updated</TableHead>
            <TableHead className="w-40 text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {collections.map((collection) => (
            <TableRow key={collection.id}>
              <TableCell>
                <div className="font-medium">{collection.name}</div>
                <div className="mt-0.5 max-w-xl truncate font-mono text-xs text-muted-foreground">
                  {collection.query}
                </div>
              </TableCell>
              <TableCell className="max-w-xs">
                {collection.description ? (
                  <span className="line-clamp-2 text-muted-foreground">
                    {collection.description}
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell>
                <Badge
                  variant={
                    collection.status === "valid" ? "outline" : "destructive"
                  }
                >
                  {collection.status}
                </Badge>
              </TableCell>
              <TableCell>{formatDate(collection.updated_at)}</TableCell>
              <TableCell>
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={`/collections/${collection.id}`}>View</Link>
                  </Button>
                  {isAdmin ? (
                    <>
                      <EditCollectionDialog collection={collection} />
                      <DeleteCollectionDialog collection={collection} />
                    </>
                  ) : null}
                </div>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}
