import * as React from "react"
import { DndContext, DragOverlay, pointerWithin } from "@dnd-kit/core"
import {
  Database,
  FileQuestion,
  Folder,
  Home,
  RefreshCw,
} from "lucide-react"
import { Link, useNavigate, useParams } from "react-router"

import { FileActionsProvider } from "@/components/filesystem/file-actions-provider"
import { FolderActionsProvider } from "@/components/filesystem/folder-actions-provider"
import { FolderEntriesTable } from "@/components/filesystem/folder-entries-table"
import { OffsetPaginationBar } from "@/components/pagination-offset"
import { FolderHeaderActions } from "@/components/filesystem/folder-header-actions"
import { FileTree } from "@/components/filesystem/file-tree"
import { SidebarFooter } from "@/components/layout/sidebar-footer"
import { SidebarHeader } from "@/components/layout/sidebar-header"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { FolderDragStateProvider } from "@/components/filesystem/folder-drag-state-provider"
import { useFolderDnd } from "@/hooks/use-folder-dnd"
import {
  FOLDER_FILES_PAGE_SIZE,
  useFolderFiles,
  useFolderStats,
  useFolderTree,
} from "@/hooks/use-filesystem"
import { useUpdateFolder } from "@/hooks/use-folders"
import { useNativeFileDrop } from "@/hooks/use-native-file-drop"
import { extractApiError } from "@/lib/api"
import { formatBytes } from "@/lib/format"
import { PERM, can } from "@/lib/permissions"
import { cn } from "@/lib/utils"
import type {
  FileSystemEntry,
  FileSystemFile,
  FolderContentsSortState,
  FolderStats,
  FolderTreeNode,
  PaginatedFilesResponse,
} from "@/types/filesystem"

export function FilesystemPage() {
  return (
    <FolderActionsProvider>
      <FileActionsProvider>
        <FilesystemPageInner />
      </FileActionsProvider>
    </FolderActionsProvider>
  )
}

function FilesystemPageInner() {
  const params = useParams()
  const navigate = useNavigate()
  const routeFolderId = params.folderId
  const folderTree = useFolderTree()
  const selectedFolder = React.useMemo(
    () =>
      routeFolderId
        ? findFolderById(folderTree.data, routeFolderId)
        : folderTree.data,
    [folderTree.data, routeFolderId]
  )
  const [fileOffset, setFileOffset] = React.useState(0)
  const [sort, setSort] = React.useState<FolderContentsSortState>({
    key: "name",
    dir: "asc",
  })

  /* Pagination offset is driven by folder/sort and server totals; syncing via effects is intentional. */
  /* eslint-disable react-hooks/set-state-in-effect -- see comment above */
  React.useEffect(() => {
    setFileOffset(0)
  }, [selectedFolder?.id, sort.key, sort.dir])

  const folderFiles = useFolderFiles(selectedFolder?.id, {
    offset: fileOffset,
    sort: sort.key,
    dir: sort.dir,
    limit: FOLDER_FILES_PAGE_SIZE,
  })
  const folderStats = useFolderStats(selectedFolder?.id)

  React.useEffect(() => {
    const page = folderFiles.data
    if (!page || page.total === 0) return
    if (page.offset >= page.total) {
      const last = Math.max(
        0,
        Math.floor((page.total - 1) / page.limit) * page.limit
      )
      setFileOffset(last)
    }
  }, [folderFiles.data])
  /* eslint-enable react-hooks/set-state-in-effect */

  const expandedFolderIds = React.useMemo(
    () => getExpandedFolderIds(folderTree.data, selectedFolder?.id),
    [folderTree.data, selectedFolder?.id]
  )
  const entries = React.useMemo(() => {
    const items = folderFiles.data?.items ?? []
    return selectedFolder ? buildFolderEntries(selectedFolder, items) : []
  }, [folderFiles.data, selectedFolder])
  const folderChildCount = selectedFolder?.children.length ?? 0
  const filesTotal = folderFiles.data?.total ?? 0
  const mainNativeDrop = useNativeFileDrop({
    folderId: selectedFolder?.id ?? "",
    disabled:
      !selectedFolder || !can(selectedFolder.effective_permissions, PERM.WRITE),
  })

  const dnd = useFolderDnd({ tree: folderTree.data })

  function handleAfterDeleteSelected() {
    if (!selectedFolder || selectedFolder.parent_id === null) {
      navigate("/", { replace: true })
      return
    }
    navigate("/", { replace: true })
  }

  return (
    <DndContext
      sensors={dnd.sensors}
      collisionDetection={pointerWithin}
      onDragStart={dnd.onDragStart}
      onDragCancel={dnd.onDragCancel}
      onDragEnd={dnd.onDragEnd}
    >
      <FolderDragStateProvider state={dnd.dragState}>
        <div
          className={cn(
            "flex min-h-svh flex-col bg-background text-foreground",
            "lg:grid lg:h-dvh lg:max-h-dvh lg:grid-cols-[20rem_1fr] lg:grid-rows-[minmax(0,1fr)] lg:overflow-hidden"
          )}
        >
          <aside className="flex min-h-0 flex-col border-b bg-sidebar p-4 lg:min-h-0 lg:border-r lg:border-b-0">
            <SidebarHeader />
            <div className="min-h-0 overflow-y-auto lg:flex-1">
              {folderTree.isLoading ? (
                <TreeSkeleton />
              ) : folderTree.isError ? (
                <ErrorState
                  title="Could not load folders"
                  message={extractApiError(folderTree.error)}
                  onRetry={() => void folderTree.refetch()}
                />
              ) : folderTree.data ? (
                <FileTree
                  key={selectedFolder?.id}
                  root={folderTree.data}
                  selectedFolderId={selectedFolder?.id}
                  expandedFolderIds={expandedFolderIds}
                />
              ) : null}
            </div>
            <SidebarFooter />
          </aside>

          <main
            {...mainNativeDrop.handlers}
            className={cn(
              "min-h-0 min-w-0 overflow-y-auto p-4 lg:p-8 transition-colors",
              mainNativeDrop.isOver &&
                "ring-2 ring-inset ring-primary/40 bg-primary/5"
            )}
          >
              <div className="mx-auto max-w-6xl space-y-6">
                <div className="space-y-3">
                  <FilesystemBreadcrumbs
                    root={folderTree.data}
                    selectedFolder={selectedFolder}
                  />
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <FolderTitle
                        key={selectedFolder?.id ?? "root"}
                        folder={selectedFolder}
                      />
                      <p className="text-sm text-muted-foreground">
                        Browse, organize, and manage folders.
                      </p>
                    </div>
                    {selectedFolder && (
                      <FolderHeaderActions
                        folder={selectedFolder}
                        onAfterDelete={handleAfterDeleteSelected}
                      />
                    )}
                  </div>
                </div>

                <Card>
                  <CardHeader className="gap-3 sm:flex sm:flex-row sm:items-center sm:justify-between">
                    <CardTitle>Folder Contents</CardTitle>
                    {selectedFolder && (
                      <div className="text-xs text-muted-foreground">
                        {folderFiles.isLoading ? (
                          <Skeleton className="h-4 w-36" />
                        ) : folderFiles.isError ? null : (
                          <>
                            {folderChildCount.toLocaleString()}{" "}
                            {folderChildCount === 1 ? "folder" : "folders"}
                            {" · "}
                            {filesTotal.toLocaleString()}{" "}
                            {filesTotal === 1 ? "file" : "files"}
                            <FolderRecursiveSummary
                              stats={folderStats.data}
                              isLoading={folderStats.isLoading}
                            />
                          </>
                        )}
                      </div>
                    )}
                  </CardHeader>
                  <CardContent>
                    {renderContentState({
                      entries,
                      folderChildCount,
                      filesTotal,
                      filesPage: folderFiles.data,
                      folderFilesError: folderFiles.error,
                      isFilesError: folderFiles.isError,
                      isFilesLoading: folderFiles.isLoading,
                      isFolderMissing:
                        !folderTree.isLoading &&
                        folderTree.data !== undefined &&
                        !selectedFolder,
                      onRetryFiles: () => void folderFiles.refetch(),
                      onFilesOffsetChange: setFileOffset,
                      sort,
                      onSortChange: setSort,
                    })}
                  </CardContent>
                </Card>
              </div>
          </main>
        </div>
        <DragOverlay dropAnimation={null}>
          {dnd.activeFolder ? (
            <div className="pointer-events-none flex items-center gap-2 rounded-md border bg-popover px-3 py-1.5 text-xs shadow-lg">
              <Folder className="size-3.5 text-muted-foreground" />
              <span className="font-medium">{dnd.activeFolder.name}</span>
            </div>
          ) : null}
        </DragOverlay>
      </FolderDragStateProvider>
    </DndContext>
  )
}

function FolderTitle({ folder }: { folder: FolderTreeNode | undefined }) {
  const rename = useUpdateFolder()
  const canRename =
    folder !== undefined &&
    folder.parent_id !== null &&
    can(folder.effective_permissions, PERM.WRITE)
  const [editing, setEditing] = React.useState(false)
  const [draftName, setDraftName] = React.useState(folder?.name ?? "")
  const renameCommitRef = React.useRef(false)

  async function commitRename() {
    if (!folder || renameCommitRef.current) return
    const trimmed = draftName.trim()
    if (!trimmed) {
      setDraftName(folder.name)
      setEditing(false)
      return
    }
    if (trimmed === folder.name) {
      setEditing(false)
      return
    }
    renameCommitRef.current = true
    try {
      await rename.mutateAsync({ id: folder.id, name: trimmed })
      setEditing(false)
    } catch {
      setDraftName(folder.name)
      // useUpdateFolder toasts the error
    } finally {
      renameCommitRef.current = false
    }
  }

  function cancelRename() {
    setDraftName(folder?.name ?? "")
    setEditing(false)
  }

  if (!folder || !canRename) {
    return (
      <h1 className="text-2xl font-semibold tracking-tight">
        {folder?.name || "Filesystem"}
      </h1>
    )
  }

  if (editing) {
    return (
      <Input
        value={draftName}
        onChange={(event) => setDraftName(event.target.value)}
        onBlur={() => void commitRename()}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault()
            cancelRename()
          } else if (event.key === "Enter") {
            event.preventDefault()
            void commitRename()
          }
        }}
        disabled={rename.isPending}
        className="h-9 max-w-md text-2xl font-semibold tracking-tight"
        autoFocus
        onFocus={(event) => event.target.select()}
      />
    )
  }

  return (
    <button
      type="button"
      className="text-left text-2xl font-semibold tracking-tight hover:underline"
      onDoubleClick={() => {
        setDraftName(folder.name)
        setEditing(true)
      }}
    >
      {folder.name}
    </button>
  )
}

type ContentStateProps = {
  entries: FileSystemEntry[]
  folderChildCount: number
  filesTotal: number
  filesPage: PaginatedFilesResponse | undefined
  folderFilesError: unknown
  isFilesError: boolean
  isFilesLoading: boolean
  isFolderMissing: boolean
  onRetryFiles: () => void
  onFilesOffsetChange: (offset: number) => void
  sort: FolderContentsSortState
  onSortChange: (next: FolderContentsSortState) => void
}

function renderContentState({
  entries,
  folderChildCount,
  filesTotal,
  filesPage,
  folderFilesError,
  isFilesError,
  isFilesLoading,
  isFolderMissing,
  onRetryFiles,
  onFilesOffsetChange,
  sort,
  onSortChange,
}: ContentStateProps) {
  if (isFolderMissing) {
    return (
      <EmptyState
        icon={FileQuestion}
        title="Folder not found"
        message="No folder matches this path in the filesystem tree."
      />
    )
  }

  if (isFilesLoading) {
    return <ContentSkeleton />
  }

  if (isFilesError) {
    return (
      <ErrorState
        title="Could not load files"
        message={extractApiError(folderFilesError)}
        onRetry={onRetryFiles}
      />
    )
  }

  if (folderChildCount === 0 && filesTotal === 0) {
    return (
      <EmptyState
        icon={Database}
        title="This folder is empty"
        message="Sub-folders and files will appear here when they are created."
      />
    )
  }

  return (
    <>
      <FolderEntriesTable
        entries={entries}
        sort={sort}
        onSortChange={onSortChange}
      />
      {filesPage && filesPage.total > filesPage.limit ? (
        <OffsetPaginationBar
          total={filesPage.total}
          limit={filesPage.limit}
          offset={filesPage.offset}
          onChange={onFilesOffsetChange}
        />
      ) : null}
    </>
  )
}

function FilesystemBreadcrumbs({
  root,
  selectedFolder,
}: {
  root: FolderTreeNode | undefined
  selectedFolder: FolderTreeNode | undefined
}) {
  const pathSegments = selectedFolder ? parsePathSegments(selectedFolder.path) : []
  const parts = buildBreadcrumbParts(root, selectedFolder, pathSegments)

  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          {selectedFolder?.parent_id === null || pathSegments.length === 0 ? (
            <BreadcrumbPage className="inline-flex items-center gap-1">
              <Home className="size-3.5" />
              Root
            </BreadcrumbPage>
          ) : (
            <BreadcrumbLink asChild>
              <Link to="/" className="inline-flex items-center gap-1">
                <Home className="size-3.5" />
                Root
              </Link>
            </BreadcrumbLink>
          )}
        </BreadcrumbItem>
        {parts.map((part) => (
          <React.Fragment key={part.key}>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              {part.current ? (
                <BreadcrumbPage>{part.label}</BreadcrumbPage>
              ) : part.href ? (
                <BreadcrumbLink asChild>
                  <Link to={part.href}>{part.label}</Link>
                </BreadcrumbLink>
              ) : (
                <span className="text-muted-foreground">{part.label}</span>
              )}
            </BreadcrumbItem>
          </React.Fragment>
        ))}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

function FolderRecursiveSummary({
  stats,
  isLoading,
}: {
  stats: FolderStats | undefined
  isLoading: boolean
}) {
  if (isLoading) {
    return (
      <>
        {" · "}
        <Skeleton className="inline-block h-3 w-20 align-middle" />
      </>
    )
  }
  if (!stats || stats.file_count === 0) {
    return null
  }
  const coveragePct =
    stats.enrichment_coverage !== null
      ? Math.round(stats.enrichment_coverage * 100)
      : null
  return (
    <span title="Totals across this folder and all subfolders">
      {" · "}
      {formatBytes(stats.logical_size_bytes)}
      {coveragePct !== null ? ` · ${coveragePct}% enriched` : ""}
    </span>
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

function EmptyState({
  icon: Icon,
  title,
  message,
}: {
  icon: React.ElementType
  title: string
  message: string
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-dashed px-4 py-12 text-center">
      <Icon className="size-8 text-muted-foreground" />
      <div className="mt-3 text-sm font-medium">{title}</div>
      <p className="mt-1 max-w-sm text-xs text-muted-foreground">{message}</p>
    </div>
  )
}

function TreeSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 7 }).map((_, index) => (
        <Skeleton
          key={index}
          className={cn("h-8", index > 0 && index < 5 && "ml-5")}
        />
      ))}
    </div>
  )
}

function ContentSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 5 }).map((_, index) => (
        <React.Fragment key={index}>
          <div className="flex items-center gap-3">
            <Skeleton className="size-9" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-3 w-1/4" />
            </div>
            <Skeleton className="h-4 w-16" />
          </div>
          {index < 4 && <Separator />}
        </React.Fragment>
      ))}
    </div>
  )
}

function buildFolderEntries(
  folder: FolderTreeNode,
  files: FileSystemFile[]
): FileSystemEntry[] {
  const folderEntries = folder.children.map<FileSystemEntry>((child) => ({
    kind: "folder",
    id: child.id,
    name: child.name,
    href: buildFolderRoute(child),
    child_count: child.children.length,
    node: child,
  }))
  const fileEntries = files.map<FileSystemEntry>((file) => ({
    kind: "file",
    id: file.id,
    name: file.name,
    size: file.size_bytes,
    mime_type: file.mimetype,
    updated_at: file.updated_at,
    file,
    folder,
  }))

  return [...folderEntries, ...fileEntries]
}

function getExpandedFolderIds(
  root: FolderTreeNode | undefined,
  selectedFolderId: string | undefined
) {
  const ids = selectedFolderId
    ? getDisplayedAncestorIds(root, selectedFolderId)
    : new Set<string>()
  if (root) {
    ids.add(root.id)
  }
  return ids
}

function getDisplayedAncestorIds(
  folder: FolderTreeNode | undefined,
  selectedFolderId: string
): Set<string> {
  if (!folder) {
    return new Set()
  }

  if (folder.id === selectedFolderId) {
    return new Set([folder.id])
  }

  for (const child of folder.children) {
    const ids = getDisplayedAncestorIds(child, selectedFolderId)
    if (ids.size > 0) {
      ids.add(folder.id)
      return ids
    }
  }

  return new Set()
}

function findFolderById(
  folder: FolderTreeNode | undefined,
  folderId: string
): FolderTreeNode | undefined {
  if (!folder) {
    return undefined
  }

  if (folder.id === folderId) {
    return folder
  }

  for (const child of folder.children) {
    const match = findFolderById(child, folderId)
    if (match) {
      return match
    }
  }

  return undefined
}

type BreadcrumbPart = {
  key: string
  label: string
  current: boolean
  href?: string
}

function buildBreadcrumbParts(
  root: FolderTreeNode | undefined,
  selectedFolder: FolderTreeNode | undefined,
  pathSegments: string[]
): BreadcrumbPart[] {
  const parts: BreadcrumbPart[] = []
  let hiddenInserted = false

  for (let index = 0; index < pathSegments.length; index += 1) {
    const segment = pathSegments[index]
    const isLast = index === pathSegments.length - 1
    const visibleFolder = findFolderByPath(root, pathSegments.slice(0, index + 1))

    if (!visibleFolder) {
      if (!hiddenInserted) {
        parts.push({
          key: `hidden-${index}`,
          label: "…",
          current: false,
        })
        hiddenInserted = true
      }
      continue
    }

    parts.push({
      key: visibleFolder.id,
      label: segment,
      current: isLast,
      href: isLast ? undefined : buildFolderRoute(visibleFolder),
    })
  }

  if (parts.length === 0 && selectedFolder && selectedFolder.parent_id !== null) {
    parts.push({
      key: selectedFolder.id,
      label: selectedFolder.name,
      current: true,
    })
  }

  return parts
}

function parsePathSegments(path: string) {
  return path
    .split("/")
    .filter(Boolean)
    .map((segment) => decodeURIComponent(segment))
}

function findFolderByPath(
  root: FolderTreeNode | undefined,
  pathSegments: string[]
): FolderTreeNode | undefined {
  if (!root) {
    return undefined
  }
  if (pathSegments.length === 0) {
    return root
  }

  const [head, ...tail] = pathSegments
  const child = root.children.find((folder) => folder.name === head)
  return child ? findFolderByPath(child, tail) : undefined
}

function buildFolderRoute(folder: FolderTreeNode) {
  if (folder.parent_id === null) {
    return "/"
  }

  return `/folder/${encodeURIComponent(folder.id)}`
}
