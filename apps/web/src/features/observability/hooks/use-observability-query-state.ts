import { useCallback, useMemo, useState } from "react"
import { useSearchParams } from "react-router"

import {
  DEFAULT_OBSERVABILITY_RANGE,
  OBSERVABILITY_PAGE_SIZE,
} from "@/features/observability/lib/constants"
import {
  isTimeRangePreset,
  presetToRange,
  type TimeRangePreset,
} from "@/features/observability/lib/time-range"

export function useObservabilityQueryState() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [anchor, setAnchor] = useState(() => new Date())
  const rangeParam = searchParams.get("range")
  const range: TimeRangePreset = isTimeRangePreset(rangeParam)
    ? rangeParam
    : DEFAULT_OBSERVABILITY_RANGE
  const page = Math.max(1, Number(searchParams.get("page") ?? "1") || 1)
  const timeRange = useMemo(() => presetToRange(range, anchor), [range, anchor])
  const offset = (page - 1) * OBSERVABILITY_PAGE_SIZE

  const setRange = useCallback(
    (nextRange: TimeRangePreset) => {
      setSearchParams((current) => {
        const next = new URLSearchParams(current)
        next.set("range", nextRange)
        next.set("page", "1")
        return next
      })
      setAnchor(new Date())
    },
    [setSearchParams]
  )

  const setPage = useCallback(
    (nextPage: number) => {
      setSearchParams((current) => {
        const next = new URLSearchParams(current)
        next.set("page", String(Math.max(1, nextPage)))
        return next
      })
    },
    [setSearchParams]
  )

  const refreshTimeRange = useCallback(() => {
    setAnchor(new Date())
  }, [])

  return {
    range,
    page,
    timeRange,
    offset,
    pageSize: OBSERVABILITY_PAGE_SIZE,
    setRange,
    setPage,
    refreshTimeRange,
  }
}
