import { Link } from "react-router"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { CatalogObject } from "@/types/objects"

type ObjectsTableProps = {
  objects: CatalogObject[]
}

export function ObjectsTable({ objects }: ObjectsTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Key</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Storage</TableHead>
            <TableHead>ETag</TableHead>
            <TableHead>Modified</TableHead>
            <TableHead>Last seen</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {objects.map((object) => (
            <TableRow key={object.id}>
              <TableCell>
                <Link
                  className="block max-w-80 truncate font-medium underline-offset-4 hover:underline"
                  to={`/objects/${object.id}`}
                >
                  {object.key}
                </Link>
              </TableCell>
              <TableCell>{formatSize(object.attributes.upstream?.size)}</TableCell>
              <TableCell>
                {object.attributes.upstream?.s3?.storage_class ?? (
                  <span className="text-muted-foreground">-</span>
                )}
              </TableCell>
              <TableCell>
                <div className="max-w-52 truncate font-mono text-[11px]">
                  {object.attributes.upstream?.etag ?? "-"}
                </div>
              </TableCell>
              <TableCell>
                {formatOptionalDate(object.attributes.upstream?.last_modified)}
              </TableCell>
              <TableCell>{formatOptionalDate(object.last_seen_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function formatSize(value: number | undefined) {
  if (value === undefined) {
    return <span className="text-muted-foreground">-</span>
  }

  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: 1,
    notation: value >= 1024 * 1024 * 1024 ? "compact" : "standard",
    style: "unit",
    unit: "byte",
    unitDisplay: "narrow",
  }).format(value)
}

function formatOptionalDate(value: string | undefined) {
  if (!value) {
    return <span className="text-muted-foreground">-</span>
  }

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}
