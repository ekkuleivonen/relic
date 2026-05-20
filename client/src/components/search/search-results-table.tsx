import { File as FileIcon } from "lucide-react"
import { Link } from "react-router"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { buildMetaEqFilter } from "@/lib/file-meta"
import { buildSingleFilterHref } from "@/lib/search-query"
import { formatBytes, formatRelativeTime } from "@/lib/format"
import { metaPreview } from "@/lib/file-meta"
import type { FileSystemFile } from "@/types/filesystem"
import type { SearchQuery } from "@/types/search"

type SearchResultsTableProps = {
  files: FileSystemFile[]
  query: SearchQuery
  onChange: (next: SearchQuery) => void
}

export function SearchResultsTable({
  files,
  query,
  onChange,
}: SearchResultsTableProps) {
  return (
    <div className="overflow-hidden rounded-md border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="w-10 pl-3" />
            <TableHead>Name</TableHead>
            <TableHead className="w-44">Type</TableHead>
            <TableHead className="w-24 text-right">Size</TableHead>
            <TableHead className="w-32 pr-3 text-right">Updated</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {files.map((file) => (
            <ResultRow
              key={file.id}
              file={file}
              query={query}
              onChange={onChange}
            />
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

type ResultRowProps = {
  file: FileSystemFile
  query: SearchQuery
  onChange: (next: SearchQuery) => void
}

function ResultRow({ file, query, onChange }: ResultRowProps) {
  const detailHref = `/file/${encodeURIComponent(file.id)}`
  const preview = metaPreview(file.meta)

  return (
    <TableRow>
      <TableCell className="pl-3 align-top">
        <RowIcon />
      </TableCell>
      <TableCell className="align-top">
        <div className="space-y-1">
          <Link
            to={detailHref}
            className="block font-medium hover:underline"
            draggable={false}
          >
            {file.name}
          </Link>
          {preview.length > 0 && (
            <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
              {preview.map((item) => {
                const filter = buildMetaEqFilter(item.path, item.display)
                const isActive = query.meta.some(
                  (active) =>
                    active.key === filter.key &&
                    active.op === filter.op &&
                    active.value.toLowerCase() === filter.value.toLowerCase()
                )
                return (
                  <button
                    key={item.path}
                    type="button"
                    onClick={() =>
                      onChange({
                        ...query,
                        meta: toggleMetaFilter(query.meta, filter),
                        offset: 0,
                      })
                    }
                    className={
                      isActive
                        ? "text-primary"
                        : "hover:text-foreground"
                    }
                    title={`Filter by ${item.path}`}
                  >
                    <span className="font-mono text-[0.625rem] text-muted-foreground/80">
                      {item.path}
                    </span>
                    {": "}
                    <span>{item.display}</span>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </TableCell>
      <TableCell className="align-top text-xs text-muted-foreground">
        {file.mimetype ? (
          <Link
            to={buildSingleFilterHref({
              mimetypes: [file.mimetype],
            })}
            className="hover:underline"
          >
            {file.mimetype}
          </Link>
        ) : (
          "—"
        )}
        {file.extension && (
          <div>
            <Link
              to={buildSingleFilterHref({
                extensions: [file.extension],
              })}
              className="text-[0.625rem] uppercase hover:underline"
            >
              .{file.extension}
            </Link>
          </div>
        )}
      </TableCell>
      <TableCell className="align-top text-right text-xs text-muted-foreground">
        {formatBytes(file.size_bytes)}
      </TableCell>
      <TableCell className="align-top pr-3 text-right text-xs text-muted-foreground">
        {formatRelativeTime(file.updated_at)}
      </TableCell>
    </TableRow>
  )
}

function toggleMetaFilter(
  filters: SearchQuery["meta"],
  candidate: SearchQuery["meta"][number]
) {
  const idx = filters.findIndex(
    (filter) =>
      filter.key === candidate.key &&
      filter.op === candidate.op &&
      filter.value === candidate.value
  )
  if (idx === -1) return [...filters, candidate]
  return filters.filter((_, i) => i !== idx)
}

function RowIcon() {
  return (
    <div className="flex size-7 items-center justify-center rounded-md bg-muted text-muted-foreground">
      <FileIcon className="size-3.5" />
    </div>
  )
}
