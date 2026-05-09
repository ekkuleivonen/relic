import { Skeleton } from "@/components/ui/skeleton"
import { extractApiError } from "@/lib/api"
import { toggleStringFilter } from "@/lib/search-query"
import { cn } from "@/lib/utils"
import type { FacetValue, Facets, SearchQuery } from "@/types/search"

type FacetSidebarProps = {
  facets: Facets | undefined
  isLoading: boolean
  isError: boolean
  error?: unknown
  query: SearchQuery
  onChange: (next: SearchQuery) => void
  className?: string
}

/** Faceted browsing panel. Each axis (tags, MIME, extension) shows top values
 * with their counts; clicking toggles that value in the matching SearchQuery
 * filter. Facet counts are drillsight (the active filter on the same axis is
 * ignored when computing counts) so the panel keeps working as the user
 * narrows. */
export function FacetSidebar({
  facets,
  isLoading,
  isError,
  error,
  query,
  onChange,
  className,
}: FacetSidebarProps) {
  if (isLoading && !facets) {
    return (
      <div className={cn("space-y-6", className)}>
        <FacetGroupSkeleton title="Tags" />
        <FacetGroupSkeleton title="MIME type" />
        <FacetGroupSkeleton title="Extension" />
      </div>
    )
  }

  if (isError) {
    return (
      <div
        className={cn(
          "rounded-md border border-destructive/20 bg-destructive/5 p-3 text-xs text-destructive",
          className
        )}
      >
        Could not load facets: {extractApiError(error)}
      </div>
    )
  }

  if (!facets) {
    return null
  }

  const allEmpty =
    facets.tags.length === 0 &&
    facets.mimetypes.length === 0 &&
    facets.extensions.length === 0

  if (allEmpty) {
    return (
      <div className={cn("text-xs text-muted-foreground", className)}>
        No facets to show. Try widening your query.
      </div>
    )
  }

  return (
    <div className={cn("space-y-6", className)}>
      <FacetGroup
        title="Tags"
        values={facets.tags}
        selected={query.tags}
        onToggle={(value) =>
          onChange({
            ...query,
            tags: toggleStringFilter(query.tags, value),
            offset: 0,
          })
        }
        emptyMessage="No tags yet."
      />
      <FacetGroup
        title="MIME type"
        values={facets.mimetypes}
        selected={query.mimetypes}
        onToggle={(value) =>
          onChange({
            ...query,
            mimetypes: toggleStringFilter(query.mimetypes, value),
            offset: 0,
          })
        }
      />
      <FacetGroup
        title="Extension"
        values={facets.extensions}
        selected={query.extensions}
        onToggle={(value) =>
          onChange({
            ...query,
            extensions: toggleStringFilter(query.extensions, value),
            offset: 0,
          })
        }
        valuePrefix="."
      />
    </div>
  )
}

type FacetGroupProps = {
  title: string
  values: FacetValue[]
  selected: string[]
  onToggle: (value: string) => void
  valuePrefix?: string
  emptyMessage?: string
}

function FacetGroup({
  title,
  values,
  selected,
  onToggle,
  valuePrefix = "",
  emptyMessage = "—",
}: FacetGroupProps) {
  const selectedSet = new Set(selected.map((value) => value.toLowerCase()))

  return (
    <section>
      <h3 className="mb-2 text-[0.625rem] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      {values.length === 0 ? (
        <p className="text-xs text-muted-foreground">{emptyMessage}</p>
      ) : (
        <ul className="space-y-0.5">
          {values.map((value) => {
            const isSelected = selectedSet.has(value.value.toLowerCase())
            return (
              <li key={value.value}>
                <button
                  type="button"
                  onClick={() => onToggle(value.value)}
                  className={cn(
                    "group flex w-full items-center gap-2 rounded-md px-2 py-1 text-left text-xs transition-colors",
                    isSelected
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <span
                    aria-hidden="true"
                    className={cn(
                      "size-3 shrink-0 rounded-sm border",
                      isSelected
                        ? "border-primary bg-primary"
                        : "border-input bg-input/30 group-hover:border-foreground/30"
                    )}
                  />
                  <span className="min-w-0 flex-1 truncate">
                    {valuePrefix}
                    {value.value}
                  </span>
                  <span
                    className={cn(
                      "shrink-0 tabular-nums",
                      isSelected ? "text-primary" : "text-muted-foreground/70"
                    )}
                  >
                    {value.count}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function FacetGroupSkeleton({ title }: { title: string }) {
  return (
    <section>
      <h3 className="mb-2 text-[0.625rem] font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <div className="space-y-1.5">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-5 w-full" />
        ))}
      </div>
    </section>
  )
}
