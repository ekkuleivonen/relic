import * as React from "react"

export type SearchPaletteContextValue = {
  open: () => void
  close: () => void
  toggle: () => void
}

export const SearchPaletteContext =
  React.createContext<SearchPaletteContextValue | null>(null)

/** Access the global search palette controller. Must be called inside a
 * `SearchPaletteProvider`; throws otherwise so missing wiring fails fast. */
export function useSearchPalette(): SearchPaletteContextValue {
  const ctx = React.useContext(SearchPaletteContext)
  if (!ctx) {
    throw new Error(
      "useSearchPalette must be used inside <SearchPaletteProvider>"
    )
  }
  return ctx
}
