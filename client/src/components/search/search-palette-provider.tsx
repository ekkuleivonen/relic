import * as React from "react"
import { useNavigate } from "react-router"

import { SearchPaletteDialog } from "@/components/search/search-palette-dialog"
import {
  SearchPaletteContext,
  type SearchPaletteContextValue,
} from "@/hooks/use-search-palette"
import type { FolderTreeNode } from "@/types/filesystem"

/** Global search palette host. Mounts the Cmd+K dialog once, registers the
 * hotkey, and exposes `open/close/toggle` to descendants via context so any
 * trigger (sidebar icon, breadcrumb, etc.) can open it without prop drilling. */
export function SearchPaletteProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [open, setOpen] = React.useState(false)
  const navigate = useNavigate()

  const value = React.useMemo<SearchPaletteContextValue>(
    () => ({
      open: () => setOpen(true),
      close: () => setOpen(false),
      toggle: () => setOpen((prev) => !prev),
    }),
    []
  )

  React.useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "k") return
      if (!event.metaKey && !event.ctrlKey) return
      // The shortcut is unambiguous so we honor it even when an input is
      // focused — that's the whole point of a global jump-to-search.
      event.preventDefault()
      setOpen((prev) => !prev)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  function handleSelectFile(fileId: string) {
    setOpen(false)
    navigate(`/file/${encodeURIComponent(fileId)}`)
  }

  function handleSelectFolder(folder: FolderTreeNode) {
    setOpen(false)
    // Root has no dedicated route — going there means the filesystem index.
    navigate(
      folder.parent_id === null
        ? "/"
        : `/folder/${encodeURIComponent(folder.id)}`
    )
  }

  function handleSelectAllResults(href: string) {
    setOpen(false)
    navigate(href)
  }

  return (
    <SearchPaletteContext.Provider value={value}>
      {children}
      <SearchPaletteDialog
        open={open}
        onOpenChange={setOpen}
        onSelectFile={handleSelectFile}
        onSelectFolder={handleSelectFolder}
        onSelectAllResults={handleSelectAllResults}
      />
    </SearchPaletteContext.Provider>
  )
}
