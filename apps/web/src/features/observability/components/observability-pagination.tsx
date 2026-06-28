import { Button } from "@/components/ui/button"
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination"

type ObservabilityPaginationProps = {
  total: number
  page: number
  pageSize: number
  onPageChange: (page: number) => void
}

export function ObservabilityPagination({
  total,
  page,
  pageSize,
  onPageChange,
}: ObservabilityPaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize))
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, total)

  if (total === 0) {
    return null
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="text-sm text-muted-foreground">
        Showing {start}–{end} of {total}
      </p>
      <Pagination className="mx-0 w-auto justify-end">
        <PaginationContent>
          <PaginationItem>
            <PaginationPrevious
              href="#"
              onClick={(event) => {
                event.preventDefault()
                if (page > 1) {
                  onPageChange(page - 1)
                }
              }}
              aria-disabled={page <= 1}
              className={page <= 1 ? "pointer-events-none opacity-50" : undefined}
            />
          </PaginationItem>
          {buildPageItems(page, pageCount).map((item, index) =>
            item === "ellipsis" ? (
              <PaginationItem key={`ellipsis-${index}`}>
                <PaginationEllipsis />
              </PaginationItem>
            ) : (
              <PaginationItem key={item}>
                <Button
                  variant={item === page ? "outline" : "ghost"}
                  size="icon"
                  onClick={() => onPageChange(item)}
                >
                  {item}
                </Button>
              </PaginationItem>
            )
          )}
          <PaginationItem>
            <PaginationNext
              href="#"
              onClick={(event) => {
                event.preventDefault()
                if (page < pageCount) {
                  onPageChange(page + 1)
                }
              }}
              aria-disabled={page >= pageCount}
              className={
                page >= pageCount ? "pointer-events-none opacity-50" : undefined
              }
            />
          </PaginationItem>
        </PaginationContent>
      </Pagination>
    </div>
  )
}

function buildPageItems(page: number, pageCount: number) {
  if (pageCount <= 5) {
    return Array.from({ length: pageCount }, (_, index) => index + 1)
  }

  const items: Array<number | "ellipsis"> = [1]
  if (page > 3) {
    items.push("ellipsis")
  }

  const start = Math.max(2, page - 1)
  const end = Math.min(pageCount - 1, page + 1)
  for (let current = start; current <= end; current += 1) {
    items.push(current)
  }

  if (page < pageCount - 2) {
    items.push("ellipsis")
  }

  items.push(pageCount)
  return items
}
