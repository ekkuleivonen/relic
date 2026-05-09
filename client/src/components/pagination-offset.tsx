import { ChevronLeft, ChevronRight } from "lucide-react"

import { Button } from "@/components/ui/button"

export function OffsetPaginationBar({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number
  limit: number
  offset: number
  onChange: (nextOffset: number) => void
}) {
  if (total <= limit) return null
  const lastOffset = Math.max(0, Math.floor((total - 1) / limit) * limit)
  const start = total === 0 ? 0 : offset + 1
  const end = Math.min(total, offset + limit)

  return (
    <div className="mt-4 flex items-center justify-between gap-3 text-xs text-muted-foreground">
      <span>
        Showing <span className="font-medium text-foreground">{start}</span>–
        <span className="font-medium text-foreground">{end}</span> of{" "}
        <span className="font-medium text-foreground">
          {total.toLocaleString()}
        </span>
      </span>
      <div className="flex items-center gap-1.5">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange(Math.max(0, offset - limit))}
          disabled={offset === 0}
        >
          <ChevronLeft />
          Prev
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange(Math.min(lastOffset, offset + limit))}
          disabled={offset >= lastOffset}
        >
          Next
          <ChevronRight />
        </Button>
      </div>
    </div>
  )
}
