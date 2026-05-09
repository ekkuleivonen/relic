import * as React from "react"
import {
  Database,
  File,
  FileQuestion,
  Folder,
  Home,
  RefreshCw,
} from "lucide-react"
import { Link, useParams } from "react-router"

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
import { useFolderFiles, useFolderTree } from "@/hooks/use-filesystem"
import { extractApiError } from "@/lib/api"
import { cn } from "@/lib/utils"
import type {
  FileSystemEntry,
  FileSystemFile,
  FolderTreeNode,
} from "@/types/filesystem"

export function FilesystemPage() {
  const params = useParams()
  const pathSegments = React.useMemo(
    () => parsePathSegments(params["*"] ?? ""),
    [params]
  )
  const folderTree = useFolderTree()
  const selectedFolder = React.useMemo(
    () => findFolderByPath(folderTree.data, pathSegments),
    [folderTree.data, pathSegments]
  )
  const folderFiles = useFolderFiles(selectedFolder?.id)
  const expandedFolderIds = React.useMemo(
    () => getExpandedFolderIds(folderTree.data, pathSegments),
    [folderTree.data, pathSegments]
  )
  const entries = React.useMemo(
    () =>
      selectedFolder
        ? buildFolderEntries(
            selectedFolder,
            folderFiles.data ?? [],
            pathSegments
          )
        : [],
    [folderFiles.data, pathSegments, selectedFolder]
  )

  return (
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

        <main className="min-w-0 p-4 lg:p-8">
          <div className="mx-auto max-w-6xl space-y-6">
            <div className="space-y-3">
              <FilesystemBreadcrumbs pathSegments={pathSegments} />
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">
                  {selectedFolder?.name || "Filesystem"}
                </h1>
                <p className="text-sm text-muted-foreground">
                  Browse folders and blobs by URL path.
                </p>
              </div>
            </div>

            <Card>
              <CardHeader className="gap-3 sm:flex sm:flex-row sm:items-center sm:justify-between">
                <CardTitle>Folder Contents</CardTitle>
                {selectedFolder && (
                  <div className="text-xs text-muted-foreground">
                    {entries.length} {entries.length === 1 ? "item" : "items"}
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
                    !folderTree.isLoading && folderTree.data !== undefined && !selectedFolder,
                  onRetryFiles: () => void folderFiles.refetch(),
                })}
              </CardContent>
            </Card>
          </div>
        </main>
      </div>
    </div>
  )
}

type ContentStateProps = {
  entries: FileSystemEntry[]
  folderFilesError: unknown
  isFilesError: boolean
  isFilesLoading: boolean
  isFolderMissing: boolean
  onRetryFiles: () => void
}

function renderContentState({
  entries,
  folderFilesError,
  isFilesError,
  isFilesLoading,
  isFolderMissing,
  onRetryFiles,
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

  return <EntryList entries={entries} />
}

function FilesystemBreadcrumbs({ pathSegments }: { pathSegments: string[] }) {
  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          {pathSegments.length === 0 ? (
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
        {pathSegments.map((segment, index) => {
          const isLast = index === pathSegments.length - 1
          const href = buildFolderHref(pathSegments.slice(0, index + 1))

          return (
            <React.Fragment key={`${segment}-${index}`}>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                {isLast ? (
                  <BreadcrumbPage>{segment}</BreadcrumbPage>
                ) : (
                  <BreadcrumbLink asChild>
                    <Link to={href}>{segment}</Link>
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </React.Fragment>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}

function EntryList({ entries }: { entries: FileSystemEntry[] }) {
  return (
    <div className="divide-y rounded-md border">
      {entries.map((entry) => (
        <Link
          key={`${entry.kind}-${entry.id}`}
          to={entry.kind === "folder" ? entry.href : "#"}
          onClick={(event) => {
            if (entry.kind === "blob") {
              event.preventDefault()
            }
          }}
          className={cn(
            "grid grid-cols-[auto_1fr_auto] items-center gap-3 px-3 py-3 transition-colors hover:bg-muted/60",
            entry.kind === "blob" && "cursor-default"
          )}
        >
          <KindIcon kind={entry.kind} />
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{entry.name}</div>
            <div className="text-xs text-muted-foreground">
              {entry.kind === "folder"
                ? `${entry.child_count} ${entry.child_count === 1 ? "folder" : "folders"}`
                : entry.mime_type || "application/octet-stream"}
            </div>
          </div>
          <div className="text-right text-xs text-muted-foreground">
            {entry.kind === "blob" ? formatBytes(entry.size) : "Folder"}
          </div>
        </Link>
      ))}
    </div>
  )
}

function KindIcon({ kind }: { kind: FileSystemEntry["kind"] }) {
  const Icon = kind === "folder" ? Folder : File

  return (
    <div className="flex size-9 items-center justify-center rounded-md bg-muted text-muted-foreground">
      <Icon className="size-4" />
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
  files: FileSystemFile[],
  pathSegments: string[]
): FileSystemEntry[] {
  const folderEntries = [...folder.children]
    .sort((a, b) => a.name.localeCompare(b.name))
    .map<FileSystemEntry>((child) => ({
      kind: "folder",
      id: child.id,
      name: child.name,
      href: buildFolderHref([...pathSegments, child.name]),
      child_count: child.children.length,
    }))
  const fileEntries = [...files]
    .sort((a, b) => a.name.localeCompare(b.name))
    .map<FileSystemEntry>((file) => ({
      kind: "blob",
      id: file.id,
      name: file.name,
      size: file.meta.file_size,
      mime_type: file.meta.mime_type,
      updated_at: file.updated_at,
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

  return pathSegments.reduce<FolderTreeNode | undefined>((folder, segment) => {
    if (!folder) {
      return undefined
    }

    return folder.children.find((child) => child.name === segment)
  }, root)
}

function getExpandedFolderIds(
  root: FolderTreeNode | undefined,
  pathSegments: string[]
) {
  const ids = new Set<string>()
  let folder = root

  if (folder) {
    ids.add(folder.id)
  }

  for (const segment of pathSegments) {
    folder = folder?.children.find((child) => child.name === segment)
    if (!folder) {
      break
    }

    ids.add(folder.id)
  }

  return ids
}

function parsePathSegments(path: string) {
  return path
    .split("/")
    .filter(Boolean)
    .map((segment) => decodeURIComponent(segment))
}

function buildFolderHref(pathSegments: string[]) {
  if (pathSegments.length === 0) {
    return "/"
  }

  return `/${pathSegments.map(encodeURIComponent).join("/")}`
}

function formatBytes(bytes: number | undefined) {
  if (bytes === undefined) {
    return "Unknown"
  }

  if (bytes === 0) {
    return "0 B"
  }

  const units = ["B", "KB", "MB", "GB", "TB"] as const
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1)
  const value = bytes / 1024 ** exponent

  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`
}
