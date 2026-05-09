import * as React from "react"
import { ArrowDown, ArrowUp, ChevronLeft, FileSearch, RefreshCw } from "lucide-react"
import { useNavigate, useSearchParams } from "react-router"

import { OffsetPaginationBar } from "@/components/pagination-offset"
import { FacetSidebar } from "@/components/search/facet-sidebar"
import { FilterPills } from "@/components/search/filter-pills"
import { KvsFilterEditor } from "@/components/search/kvs-filter-editor"
import { SearchInput } from "@/components/search/search-input"
import { SearchResultsTable } from "@/components/search/search-results-table"
import { SidebarFooter } from "@/components/layout/sidebar-footer"
import { SidebarHeader } from "@/components/layout/sidebar-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useFolderTree } from "@/hooks/use-filesystem"
import { useFileSearch, useSearchFacets } from "@/hooks/use-search"
import { extractApiError } from "@/lib/api"
import {
  countActiveFilters,
  isEmptySearchQuery,
  parseSearchQuery,
  serializeSearchQuery,
} from "@/lib/search-query"
import { cn } from "@/lib/utils"
import type { KvsFilter, SearchOrder, SearchQuery, SearchSort } from "@/types/search"
import type { FolderTreeNode } from "@/types/filesystem"

const SORT_OPTIONS: { value: SearchSort; label: string }[] = [
  { value: "updated_at", label: "Updated" },
  { value: "created_at", label: "Created" },
  { value: "name", label: "Name" },
  { value: "size", label: "Size" },
]

export function SearchPage() {
  const [params, setParams] = useSearchParams()
  const query = React.useMemo(() => parseSearchQuery(params), [params])
  const navigate = useNavigate()
  const folderTree = useFolderTree()
  const scopeFolder = React.useMemo(
    () =>
      query.folder_id
        ? findFolderById(folderTree.data, query.folder_id)
        : undefined,
    [folderTree.data, query.folder_id]
  )

  function applyQuery(next: SearchQuery) {
    setParams(serializeSearchQuery(next))
  }

  function clearAll() {
    navigate("/search")
  }

  const search = useFileSearch(query)
  // Cap matches the backend MAX_FACET_TOP so the kvs editor and the sidebar
  // see the full long tail of values in one round trip.
  const facets = useSearchFacets(query, { top: 100 })

  const filterCount = countActiveFilters(query)
  const isEmpty = isEmptySearchQuery(query)

  return (
    <div className="h-svh overflow-hidden bg-background text-foreground">
      <div className="grid h-full min-h-0 lg:grid-cols-[20rem_1fr]">
        <aside className="flex min-h-0 flex-col overflow-hidden border-b bg-sidebar p-4 lg:border-r lg:border-b-0">
          <SidebarHeader />
          <div className="min-h-0 flex-1 overflow-y-auto pr-1">
            <FacetSidebar
              facets={facets.data}
              isLoading={facets.isLoading}
              isError={facets.isError}
              error={facets.error}
              query={query}
              onChange={applyQuery}
            />
            <div className="mt-6">
              <KvsFilterEditor
                availableKeys={facets.data?.kvs_keys ?? []}
                onAdd={(filter) =>
                  applyQuery({
                    ...query,
                    kvs: dedupeKvs([...query.kvs, filter]),
                    offset: 0,
                  })
                }
              />
            </div>
          </div>
          <SidebarFooter />
        </aside>

        <main className="min-h-0 min-w-0 overflow-y-auto">
          <div className="sticky top-0 z-10 border-b bg-background/95 px-4 py-3 backdrop-blur lg:px-8">
            <div className="mx-auto flex max-w-5xl flex-col gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="size-9 shrink-0 rounded-lg"
                  aria-label="Go back"
                  onClick={() => navigate(-1)}
                >
                  <ChevronLeft className="size-5" strokeWidth={2.25} />
                </Button>
                <SearchInput
                  value={query.q}
                  onChange={(value) =>
                    applyQuery({ ...query, q: value, offset: 0 })
                  }
                  autoFocus={isEmpty}
                  placeholder="Search by name, summary, keyword, or tag…"
                  className="min-w-0 flex-1"
                />
              </div>
              <FilterPills
                query={query}
                scopeLabel={scopeFolder?.path ?? null}
                onChange={applyQuery}
                onClearAll={clearAll}
              />
            </div>
          </div>

          <div className="mx-auto max-w-5xl px-4 py-6 lg:px-8">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <ResultsHeader
                isLoading={search.isLoading}
                isError={search.isError}
                total={search.data?.total}
                filterCount={filterCount}
              />
              <SortControls
                sort={query.sort}
                order={query.order}
                onChange={(next) => applyQuery({ ...query, ...next, offset: 0 })}
              />
            </div>

            {search.isLoading && !search.data ? (
              <ResultsSkeleton />
            ) : search.isError ? (
              <ErrorState
                title="Could not load search results"
                message={extractApiError(search.error)}
                onRetry={() => void search.refetch()}
              />
            ) : !search.data || search.data.items.length === 0 ? (
              <EmptyState query={query} />
            ) : (
              <>
                <SearchResultsTable
                  files={search.data.items}
                  query={query}
                  onChange={applyQuery}
                />
                <OffsetPaginationBar
                  total={search.data.total}
                  limit={search.data.limit}
                  offset={search.data.offset}
                  onChange={(nextOffset) =>
                    applyQuery({ ...query, offset: nextOffset })
                  }
                />
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

function ResultsHeader({
  isLoading,
  isError,
  total,
  filterCount,
}: {
  isLoading: boolean
  isError: boolean
  total: number | undefined
  filterCount: number
}) {
  if (isError) {
    return <div className="text-sm text-destructive">Search failed.</div>
  }
  if (isLoading || total === undefined) {
    return <Skeleton className="h-5 w-40" />
  }
  return (
    <div className="flex items-baseline gap-2 text-sm">
      <span className="text-base font-semibold text-foreground">
        {total.toLocaleString()}
      </span>
      <span className="text-muted-foreground">
        {total === 1 ? "result" : "results"}
      </span>
      {filterCount > 0 && (
        <Badge variant="outline" className="ml-1 font-normal">
          {filterCount} {filterCount === 1 ? "filter" : "filters"}
        </Badge>
      )}
    </div>
  )
}

type SortControlsProps = {
  sort: SearchSort
  order: SearchOrder
  onChange: (next: { sort?: SearchSort; order?: SearchOrder }) => void
}

function SortControls({ sort, order, onChange }: SortControlsProps) {
  return (
    <div className="flex items-center gap-1">
      <div className="rounded-md border bg-background p-0.5">
        {SORT_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange({ sort: option.value })}
            className={cn(
              "rounded-sm px-2 py-1 text-xs transition-colors",
              sort === option.value
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {option.label}
          </button>
        ))}
      </div>
      <Button
        type="button"
        variant="outline"
        size="icon-sm"
        onClick={() => onChange({ order: order === "asc" ? "desc" : "asc" })}
        aria-label={`Sort ${order === "asc" ? "ascending" : "descending"}`}
      >
        {order === "asc" ? <ArrowUp /> : <ArrowDown />}
      </Button>
    </div>
  )
}

function ErrorState({
  title,
  message,
  onRetry,
}: {
  title: string
  message: string
  onRetry: () => void
}) {
  return (
    <div className="rounded-md border border-destructive/20 bg-destructive/5 p-4">
      <div className="font-medium text-destructive">{title}</div>
      <p className="mt-1 text-xs text-muted-foreground">{message}</p>
      <Button className="mt-3" type="button" variant="outline" onClick={onRetry}>
        <RefreshCw className="size-3.5" />
        Retry
      </Button>
    </div>
  )
}

function EmptyState({ query }: { query: SearchQuery }) {
  const isInitial = isEmptySearchQuery(query)
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-dashed px-4 py-12 text-center">
      <FileSearch className="size-8 text-muted-foreground" />
      <div className="mt-3 text-sm font-medium">
        {isInitial ? "Search your filesystem" : "No matching files"}
      </div>
      <p className="mt-1 max-w-md text-xs text-muted-foreground">
        {isInitial
          ? "Type a query, or pick a tag from the sidebar to start exploring."
          : "Try removing a filter, or pick a different facet from the sidebar."}
      </p>
    </div>
  )
}

function ResultsSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 6 }).map((_, index) => (
        <Skeleton key={index} className="h-14 w-full" />
      ))}
    </div>
  )
}

function findFolderById(
  folder: FolderTreeNode | undefined,
  folderId: string
): FolderTreeNode | undefined {
  if (!folder) return undefined
  if (folder.id === folderId) return folder
  for (const child of folder.children) {
    const match = findFolderById(child, folderId)
    if (match) return match
  }
  return undefined
}

function dedupeKvs(filters: KvsFilter[]): KvsFilter[] {
  const seen = new Set<string>()
  const out: KvsFilter[] = []
  for (const filter of filters) {
    const key = `${filter.key}:${filter.op}:${filter.value}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(filter)
  }
  return out
}
