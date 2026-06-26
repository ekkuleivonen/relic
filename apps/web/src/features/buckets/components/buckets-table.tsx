import { Link } from "react-router"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { EditBucketDialog } from "@/features/buckets/components/edit-bucket-dialog"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { Bucket } from "@/types/buckets"

type BucketsTableProps = {
  buckets: Bucket[]
}

export function BucketsTable({ buckets }: BucketsTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Upstream</TableHead>
            <TableHead>Bucket</TableHead>
            <TableHead>Region</TableHead>
            <TableHead>Prefix</TableHead>
            <TableHead>Updated</TableHead>
            <TableHead className="w-32 text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {buckets.map((bucket) => (
            <TableRow key={bucket.id}>
              <TableCell>
                <div className="font-medium">{bucket.name}</div>
                <div className="mt-0.5 max-w-72 truncate text-muted-foreground">
                  {bucket.endpoint_url}
                </div>
              </TableCell>
              <TableCell>
                <Badge variant="outline">{bucket.upstream}</Badge>
              </TableCell>
              <TableCell>{bucket.bucket_name}</TableCell>
              <TableCell>{bucket.region}</TableCell>
              <TableCell>
                {bucket.prefix ? (
                  bucket.prefix
                ) : (
                  <span className="text-muted-foreground">All objects</span>
                )}
              </TableCell>
              <TableCell>{formatDate(bucket.updated_at)}</TableCell>
              <TableCell>
                <div className="flex justify-end gap-2">
                  <Button variant="ghost" size="sm" asChild>
                    <Link to={`/buckets/${bucket.id}`}>View</Link>
                  </Button>
                  <EditBucketDialog bucket={bucket} />
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
