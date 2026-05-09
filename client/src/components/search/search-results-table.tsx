import { File as FileIcon } from "lucide-react"
import { Link } from "react-router"

import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { buildSingleFilterHref, toggleStringFilter } from "@/lib/search-query"
import { formatBytes, formatRelativeTime } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { FileSystemFile } from "@/types/filesystem"
import type { SearchQuery } from "@/types/search"

type SearchResultsTableProps = {
  files: FileSystemFile[]
  query: SearchQuery
  onChange: (next: SearchQuery) => void
}

/** Result rows mirror the folder browser columns (icon / name / type / size /
 * updated) but include a second line of matched metadata: the summary plus
 * up to a handful of tags. Clicking any tag adds it to the active filter so
 * users can drill into similar files without retyping. */
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

const VISIBLE_TAGS = 6

function ResultRow({ file, query, onChange }: ResultRowProps) {
  const detailHref = `/file/${encodeURIComponent(file.id)}`
  const tags = file.meta.tags.slice(0, VISIBLE_TAGS)
  const overflow = file.meta.tags.length - tags.length
  const summary = file.meta.summary?.trim() || null

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
          {summary && (
            <p className="line-clamp-1 text-xs text-muted-foreground">
              {summary}
            </p>
          )}
          {tags.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {tags.map((tag) => {
                const isActive = query.tags.some(
                  (value) => value.toLowerCase() === tag.toLowerCase()
                )
                return (
                  <button
                    key={tag}
                    type="button"
                    onClick={() =>
                      onChange({
                        ...query,
                        tags: toggleStringFilter(query.tags, tag),
                        offset: 0,
                      })
                    }
                    className={cn(
                      "rounded-full border px-2 py-0.5 text-[0.625rem] font-medium transition-colors",
                      isActive
                        ? "border-primary/40 bg-primary/15 text-primary"
                        : "border-primary/20 bg-primary/10 text-primary hover:border-primary/40"
                    )}
                  >
                    {tag}
                  </button>
                )
              })}
              {overflow > 0 && (
                <Badge
                  variant="outline"
                  className="font-normal text-muted-foreground"
                >
                  +{overflow}
                </Badge>
              )}
            </div>
          )}
        </div>
      </TableCell>
      <TableCell className="align-top text-xs text-muted-foreground">
        {file.meta.mimetype ? (
          <Link
            to={buildSingleFilterHref({
              mimetypes: [file.meta.mimetype],
            })}
            className="hover:underline"
          >
            {file.meta.mimetype}
          </Link>
        ) : (
          "—"
        )}
        {file.meta.extension && (
          <div>
            <Link
              to={buildSingleFilterHref({
                extensions: [file.meta.extension],
              })}
              className="text-[0.625rem] uppercase hover:underline"
            >
              .{file.meta.extension}
            </Link>
          </div>
        )}
      </TableCell>
      <TableCell className="align-top text-right text-xs text-muted-foreground">
        {formatBytes(file.meta.size)}
      </TableCell>
      <TableCell className="align-top pr-3 text-right text-xs text-muted-foreground">
        {formatRelativeTime(file.updated_at)}
      </TableCell>
    </TableRow>
  )
}

function RowIcon() {
  return (
    <div className="flex size-7 items-center justify-center rounded-md bg-muted text-muted-foreground">
      <FileIcon className="size-3.5" />
    </div>
  )
}
