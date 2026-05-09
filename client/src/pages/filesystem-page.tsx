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
import {
  FolderEntriesTable,
  type SortState,
} from "@/components/filesystem/folder-entries-table"
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
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import { FolderDragStateProvider } from "@/components/filesystem/folder-drag-state-provider"
import { useFolderDnd } from "@/hooks/use-folder-dnd"
import { useFolderFiles, useFolderTree } from "@/hooks/use-filesystem"
import { useNativeFileDrop } from "@/hooks/use-native-file-drop"
import { extractApiError } from "@/lib/api"
import { PERM, can } from "@/lib/permissions"
import { cn } from "@/lib/utils"
import type {
  FileSystemEntry,
  FileSystemFile,
  FolderTreeNode,
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
  const legacyPathSegments = React.useMemo(
    () => parsePathSegments(params["*"] ?? ""),
    [params]
  )
  const folderTree = useFolderTree()
  const selectedFolder = React.useMemo(
    () =>
      routeFolderId
        ? findFolderById(folderTree.data, routeFolderId)
        : findFolderByPath(folderTree.data, legacyPathSegments),
    [folderTree.data, legacyPathSegments, routeFolderId]
  )
  const folderFiles = useFolderFiles(selectedFolder?.id)
  const expandedFolderIds = React.useMemo(
    () => getExpandedFolderIds(folderTree.data, selectedFolder?.id),
    [folderTree.data, selectedFolder?.id]
  )
  const entries = React.useMemo(
    () =>
      selectedFolder
        ? buildFolderEntries(selectedFolder, folderFiles.data ?? [])
        : [],
    [folderFiles.data, selectedFolder]
  )
  const mainNativeDrop = useNativeFileDrop({
    folderId: selectedFolder?.id ?? "",
    disabled:
      !selectedFolder || !can(selectedFolder.effective_permissions, PERM.WRITE),
  })
  const [sort, setSort] = React.useState<SortState>({
    key: "name",
    dir: "asc",
  })

  React.useEffect(() => {
    if (!routeFolderId && selectedFolder && legacyPathSegments.length > 0) {
      navigate(buildFolderRoute(selectedFolder), { replace: true })
    }
  }, [legacyPathSegments.length, navigate, routeFolderId, selectedFolder])

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
        <div className="min-h-svh bg-background text-foreground">
          <div className="grid min-h-svh lg:grid-cols-[20rem_1fr]">
            <aside className="flex flex-col border-b bg-sidebar p-4 lg:border-r lg:border-b-0">
              <SidebarHeader />
              <div className="flex-1">
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
                "min-w-0 p-4 lg:p-8 transition-colors",
                mainNativeDrop.isOver &&
                  "ring-2 ring-inset ring-primary/40 bg-primary/5"
              )}
            >
              <div className="mx-auto max-w-6xl space-y-6">
                <div className="space-y-3">
                  <FilesystemBreadcrumbs
                    root={folderTree.data}
                    selectedFolder={selectedFolder}
                    fallbackPathSegments={legacyPathSegments}
                  />
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h1 className="text-2xl font-semibold tracking-tight">
                        {selectedFolder?.name || "Filesystem"}
                      </h1>
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
                        {entries.length}{" "}
                        {entries.length === 1 ? "item" : "items"}
                      </div>
                    )}
                  </CardHeader>
                  <CardContent>
                    {renderContentState({
                      entries,
                      folderFilesError: folderFiles.error,
                      isFilesError: folderFiles.isError,
                      isFilesLoading: folderFiles.isLoading,
                      isFolderMissing:
                        !folderTree.isLoading &&
                        folderTree.data !== undefined &&
                        !selectedFolder,
                      onRetryFiles: () => void folderFiles.refetch(),
                      sort,
                      onSortChange: setSort,
                    })}
                  </CardContent>
                </Card>
              </div>
            </main>
          </div>
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

type ContentStateProps = {
  entries: FileSystemEntry[]
  folderFilesError: unknown
  isFilesError: boolean
  isFilesLoading: boolean
  isFolderMissing: boolean
  onRetryFiles: () => void
  sort: SortState
  onSortChange: (next: SortState) => void
}

function renderContentState({
  entries,
  folderFilesError,
  isFilesError,
  isFilesLoading,
  isFolderMissing,
  onRetryFiles,
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
        title="Could not load blobs"
        message={extractApiError(folderFilesError)}
        onRetry={onRetryFiles}
      />
    )
  }

  if (entries.length === 0) {
    return (
      <EmptyState
        icon={Database}
        title="This folder is empty"
        message="Sub-folders and blobs will appear here when they are created."
      />
    )
  }

  return (
    <FolderEntriesTable
      entries={entries}
      sort={sort}
      onSortChange={onSortChange}
    />
  )
}

function FilesystemBreadcrumbs({
  root,
  selectedFolder,
  fallbackPathSegments,
}: {
  root: FolderTreeNode | undefined
  selectedFolder: FolderTreeNode | undefined
  fallbackPathSegments: string[]
}) {
  const pathSegments = selectedFolder
    ? parsePathSegments(selectedFolder.path)
    : fallbackPathSegments
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
    kind: "blob",
    id: file.id,
    name: file.name,
    size: file.meta.size,
    mime_type: file.meta.mimetype,
    updated_at: file.updated_at,
    file,
    folder,
  }))

  return [...folderEntries, ...fileEntries]
}

function findFolderByPath(
  root: FolderTreeNode | undefined,
  pathSegments: string[]
) {
  if (!root) {
    return undefined
  }

  const targetPath = buildPathHref(pathSegments)
  return findFolderByHref(root, targetPath)
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

function findFolderByHref(
  folder: FolderTreeNode | undefined,
  href: string
): FolderTreeNode | undefined {
  if (!folder) {
    return undefined
  }

  if (buildPathHref(parsePathSegments(folder.path)) === href) {
    return folder
  }

  for (const child of folder.children) {
    const match = findFolderByHref(child, href)
    if (match) {
      return match
    }
  }

  return undefined
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

function buildPathHref(pathSegments: string[]) {
  if (pathSegments.length === 0) {
    return "/"
  }

  return `/${pathSegments.map(encodeURIComponent).join("/")}`
}

function buildFolderRoute(folder: FolderTreeNode) {
  if (folder.parent_id === null) {
    return "/"
  }

  return `/folder/${encodeURIComponent(folder.id)}`
}
