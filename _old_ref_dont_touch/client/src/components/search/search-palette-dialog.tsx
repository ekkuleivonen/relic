import * as React from "react"
import {
  ArrowRight,
  File as FileIcon,
  Folder as FolderIcon,
  Loader2,
  Search,
} from "lucide-react"

import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
} from "@/components/ui/command"
import { useFolderTree } from "@/hooks/use-filesystem"
import { useFileSearch } from "@/hooks/use-search"
import { buildSingleFilterHref } from "@/lib/search-query"
import { formatBytes } from "@/lib/format"
import { DEFAULT_SEARCH_QUERY } from "@/types/search"
import type { FolderTreeNode } from "@/types/filesystem"

const FILE_SUGGEST_LIMIT = 8
const FOLDER_SUGGEST_LIMIT = 5
const DEBOUNCE_MS = 180

type SearchPaletteDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelectFile: (fileId: string) => void
  onSelectFolder: (folder: FolderTreeNode) => void
  onSelectAllResults: (href: string) => void
}

/** Searchable command palette with file autosuggest. The first list item is
 * always "View all results", so pressing Enter on an empty selection takes
 * the user straight to the full search page. Selecting a file row navigates
 * to that file's detail page. cmdk's built-in filter is disabled because
 * matching happens on the backend. */
export function SearchPaletteDialog({
  open,
  onOpenChange,
  onSelectFile,
  onSelectFolder,
  onSelectAllResults,
}: SearchPaletteDialogProps) {
  const [draft, setDraft] = React.useState("")
  const [debounced, setDebounced] = React.useState("")
  const folderTree = useFolderTree()

  function handleOpenChange(next: boolean) {
    // Reset on close so the next open starts blank — handled at the event
    // boundary instead of in an effect to avoid a render-then-clear flash.
    if (!next) {
      setDraft("")
      setDebounced("")
    }
    onOpenChange(next)
  }

  React.useEffect(() => {
    if (draft === debounced) return
    const handle = window.setTimeout(() => {
      setDebounced(draft)
    }, DEBOUNCE_MS)
    return () => window.clearTimeout(handle)
  }, [debounced, draft])

  const trimmed = debounced.trim()
  const isActive = trimmed.length > 0

  const search = useFileSearch(
    {
      ...DEFAULT_SEARCH_QUERY,
      q: trimmed,
      limit: FILE_SUGGEST_LIMIT,
    },
    { enabled: isActive }
  )

  const folderMatches = React.useMemo(
    () => (isActive ? matchFolders(folderTree.data, trimmed) : []),
    [folderTree.data, isActive, trimmed]
  )

  const items = isActive ? (search.data?.items ?? []) : []
  const total = search.data?.total ?? 0
  const isFilesLoading = isActive && search.isFetching && !search.data
  const hasNoResults =
    isActive && !isFilesLoading && items.length === 0 && folderMatches.length === 0
  const hasMore = total > items.length
  const allResultsHref = buildSingleFilterHref({ q: trimmed })

  return (
    <CommandDialog
      title="Search files"
      description="Find files and folders by name, summary, keyword, or tag."
      open={open}
      onOpenChange={handleOpenChange}
      className="sm:max-w-3xl"
    >
      <Command shouldFilter={false}>
        <CommandInput
          value={draft}
          onValueChange={setDraft}
          placeholder="Search files and folders by name, summary, keyword, or tag…"
          autoFocus
        />
        <CommandList className="max-h-[60vh]">
          {isActive && (
            <CommandGroup heading="Search">
              <CommandItem
                value={`__all__::${trimmed}`}
                onSelect={() => onSelectAllResults(allResultsHref)}
                className="gap-2"
              >
                <Search className="size-3.5" />
                <span className="truncate">
                  Search for{" "}
                  <span className="font-medium text-foreground">
                    {`"${trimmed}"`}
                  </span>
                </span>
                <CommandShortcut className="ml-auto inline-flex items-center gap-1 text-muted-foreground">
                  <ArrowRight className="size-3" />
                  All results
                </CommandShortcut>
              </CommandItem>
            </CommandGroup>
          )}

          {isActive && folderMatches.length > 0 && (
            <CommandGroup heading="Folders">
              {folderMatches.map((folder) => (
                <CommandItem
                  key={folder.id}
                  value={`folder::${folder.id}::${folder.path}`}
                  onSelect={() => onSelectFolder(folder)}
                  className="items-start gap-2 py-2"
                >
                  <FolderIcon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate font-medium text-foreground">
                      {folder.name}
                    </span>
                    <span className="truncate font-mono text-[0.6875rem] text-muted-foreground">
                      {folder.path || "/"}
                    </span>
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          )}

          {isFilesLoading ? (
            <LoadingState />
          ) : isActive && items.length > 0 ? (
            <CommandGroup
              heading={hasMore ? `Files (${items.length} of ${total})` : "Files"}
            >
              {items.map((file) => (
                <CommandItem
                  key={file.id}
                  value={`file::${file.id}::${file.name}`}
                  onSelect={() => onSelectFile(file.id)}
                  className="items-start gap-2 py-2"
                >
                  <FileIcon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate font-medium text-foreground">
                      {file.name}
                    </span>
                    <span className="truncate text-[0.6875rem] text-muted-foreground">
                      {(typeof file.meta.summary === "string"
                        ? file.meta.summary.trim()
                        : "") ||
                        [file.mimetype, formatBytes(file.size_bytes)]
                          .filter(Boolean)
                          .join(" · ") ||
                        "No metadata yet"}
                    </span>
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}

          {hasNoResults && (
            <CommandEmpty>No files or folders match this query yet.</CommandEmpty>
          )}
          {!isActive && <EmptyHint />}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}

function LoadingState() {
  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 px-4 py-6 text-xs text-muted-foreground"
    >
      <Loader2 className="size-3.5 animate-spin" />
      Searching…
    </div>
  )
}

function EmptyHint() {
  return (
    <div className="px-4 py-6 text-center text-xs text-muted-foreground">
      <p>Type to search across every file and folder you can see.</p>
      <p className="mt-1">
        Press <kbd className="rounded border bg-muted px-1 font-mono">Enter</kbd>{" "}
        on a result to open it, or{" "}
        <kbd className="rounded border bg-muted px-1 font-mono">↑/↓</kbd> to
        navigate.
      </p>
    </div>
  )
}

/** Flatten the folder tree (skipping the unnamed root) and return up to
 * FOLDER_SUGGEST_LIMIT entries whose name or path contains the trimmed
 * query. Name matches rank above path-only matches so the most relevant
 * folder shows first; ties break alphabetically by path. */
function matchFolders(
  root: FolderTreeNode | undefined,
  query: string
): FolderTreeNode[] {
  if (!root || !query) return []
  const needle = query.toLowerCase()
  const ranked: { folder: FolderTreeNode; rank: number }[] = []
  walk(root, (folder) => {
    if (folder.parent_id === null) return
    const nameHit = folder.name.toLowerCase().includes(needle)
    const pathHit = folder.path.toLowerCase().includes(needle)
    if (!nameHit && !pathHit) return
    ranked.push({ folder, rank: nameHit ? 0 : 1 })
  })
  ranked.sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank
    return a.folder.path.localeCompare(b.folder.path)
  })
  return ranked.slice(0, FOLDER_SUGGEST_LIMIT).map((item) => item.folder)
}

function walk(
  folder: FolderTreeNode,
  visit: (folder: FolderTreeNode) => void
): void {
  visit(folder)
  for (const child of folder.children) {
    walk(child, visit)
  }
}
