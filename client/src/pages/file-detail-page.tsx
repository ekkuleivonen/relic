import * as React from "react"
import {
  Download,
  File as FileIcon,
  FileQuestion,
  Home,
  MoreHorizontal,
  RefreshCw,
} from "lucide-react"
import { Link, useParams } from "react-router"

import { FileActionsProvider } from "@/components/filesystem/file-actions-provider"
import { FileMenuItems } from "@/components/filesystem/file-menu-items"
import { FileTree } from "@/components/filesystem/file-tree"
import { SidebarFooter } from "@/components/layout/sidebar-footer"
import { SidebarHeader } from "@/components/layout/sidebar-header"
import { Badge } from "@/components/ui/badge"
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { useFile, useDownloadFile } from "@/hooks/use-files"
import { useFolderTree } from "@/hooks/use-filesystem"
import { extractApiError } from "@/lib/api"
import { formatBytes } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { FileSystemFile, FolderTreeNode } from "@/types/filesystem"

export function FileDetailPage() {
  return (
    <FileActionsProvider>
      <FileDetailPageInner />
    </FileActionsProvider>
  )
}

function FileDetailPageInner() {
  const params = useParams()
  const fileId = params.fileId
  const fileQuery = useFile(fileId)
  const folderTree = useFolderTree()
  const file = fileQuery.data
  const folder = React.useMemo(
    () =>
      file && folderTree.data
        ? findFolderById(folderTree.data, file.folder_id)
        : undefined,
    [file, folderTree.data]
  )
  const expandedFolderIds = React.useMemo(
    () =>
      file && folderTree.data
        ? getDisplayedAncestorIds(folderTree.data, file.folder_id)
        : new Set<string>(),
    [file, folderTree.data]
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
                root={folderTree.data}
                selectedFolderId={file?.folder_id}
                expandedFolderIds={expandedFolderIds}
              />
            ) : null}
          </div>
          <SidebarFooter />
        </aside>

        <main className="min-w-0 p-4 lg:p-8">
          <div className="mx-auto max-w-4xl space-y-6">
            {fileQuery.isLoading ? (
              <FileDetailSkeleton />
            ) : fileQuery.isError ? (
              <ErrorState
                title="Could not load file"
                message={extractApiError(fileQuery.error)}
                onRetry={() => void fileQuery.refetch()}
              />
            ) : file ? (
              <FileDetailContent
                file={file}
                folder={folder}
                root={folderTree.data}
              />
            ) : (
              <EmptyState
                icon={FileQuestion}
                title="File not found"
                message="No file matches this identifier."
              />
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

function FileDetailContent({
  file,
  folder,
  root,
}: {
  file: FileSystemFile
  folder: FolderTreeNode | undefined
  root: FolderTreeNode | undefined
}) {
  const download = useDownloadFile()
  const parserFileMeta = file.parser_meta.file ?? {}
  const parserSections = Object.entries(file.parser_meta).filter(
    ([key]) => key !== "file"
  )
  const ingestMeta = Object.entries(file.ingest_meta)

  return (
    <>
      <FileBreadcrumbs root={root} folder={folder} file={file} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <FileIcon className="size-4" />
            <span>File</span>
          </div>
          <h1 className="mt-1 truncate text-2xl font-semibold tracking-tight">
            {file.name}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {folder ? (
              <>
                In{" "}
                <Link
                  to={buildFolderRoute(folder)}
                  className="font-medium text-foreground hover:underline"
                >
                  {folder.path}
                </Link>
              </>
            ) : (
              "Folder unavailable"
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            onClick={() =>
              download.mutate({ file_id: file.id, filename: file.name })
            }
            disabled={download.isPending}
          >
            <Download />
            Download
          </Button>
          {folder && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="icon-sm"
                  aria-label="File actions"
                >
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-52">
                <FileMenuItems file={file} folder={folder} variant="dropdown" />
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard
          label="Status"
          value={formatParseStatus(file.parse_status)}
        />
        <StatCard label="Size" value={formatBytes(parserFileMeta.size)} />
        <StatCard
          label="Type"
          value={parserFileMeta.mime_type || "Pending parser"}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>File Details</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <DetailGrid
            rows={[
              ["File ID", file.id],
              ["Blob ID", file.blob_id],
              ["Uploaded by", file.uploaded_by],
              ["Original name", parserFileMeta.original_filename ?? file.name],
              ["Extension", parserFileMeta.extension ?? "—"],
              ["Created", formatDateTime(file.created_at)],
              ["Updated", formatDateTime(file.updated_at)],
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-2 sm:flex sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Ingest Metadata</CardTitle>
          <Badge variant="outline">{ingestMeta.length} fields</Badge>
        </CardHeader>
        <CardContent>
          {ingestMeta.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No upload-time metadata is attached to this file.
            </p>
          ) : (
            <DetailGrid rows={ingestMeta.map(([key, value]) => [key, value])} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-2 sm:flex sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Parser Metadata</CardTitle>
          <Badge variant="outline">{parserSections.length + 1} sections</Badge>
        </CardHeader>
        <CardContent className="space-y-6">
          {Object.keys(file.parser_meta).length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Parser metadata is pending.
            </p>
          ) : (
            <>
              <section>
                <h3 className="mb-3 text-sm font-medium">file</h3>
                <DetailGrid
                  rows={Object.entries(parserFileMeta).map(([key, value]) => [
                    key,
                    value,
                  ])}
                />
              </section>
              {parserSections.map(([section, value]) => (
                <section key={section}>
                  <h3 className="mb-3 text-sm font-medium">{section}</h3>
                  <pre className="overflow-auto rounded-md bg-muted p-3 text-xs">
                    {JSON.stringify(value, null, 2)}
                  </pre>
                </section>
              ))}
            </>
          )}
        </CardContent>
      </Card>
    </>
  )
}

function FileBreadcrumbs({
  root,
  folder,
  file,
}: {
  root: FolderTreeNode | undefined
  folder: FolderTreeNode | undefined
  file: FileSystemFile
}) {
  const ancestors = root && folder ? findFolderAncestors(root, folder.id) : []

  return (
    <Breadcrumb>
      <BreadcrumbList>
        <BreadcrumbItem>
          {ancestors.length <= 1 ? (
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
        {ancestors.slice(1).map((ancestor) => (
          <React.Fragment key={ancestor.id}>
            <BreadcrumbSeparator />
            <BreadcrumbItem>
              <BreadcrumbLink asChild>
                <Link to={buildFolderRoute(ancestor)}>
                  {ancestor.name || "Filesystem"}
                </Link>
              </BreadcrumbLink>
            </BreadcrumbItem>
          </React.Fragment>
        ))}
        <BreadcrumbSeparator />
        <BreadcrumbItem>
          <BreadcrumbPage>{file.name}</BreadcrumbPage>
        </BreadcrumbItem>
      </BreadcrumbList>
    </Breadcrumb>
  )
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </div>
        <div className="mt-1 truncate text-sm font-medium">{value}</div>
      </CardContent>
    </Card>
  )
}

function DetailGrid({ rows }: { rows: Array<[string, unknown]> }) {
  return (
    <dl className="grid gap-3 text-sm sm:grid-cols-[10rem_1fr]">
      {rows.map(([label, value]) => (
        <React.Fragment key={label}>
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="break-all font-mono text-xs">{formatDetailValue(value)}</dd>
        </React.Fragment>
      ))}
    </dl>
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

function FileDetailSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-5 w-72" />
      <div className="space-y-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-4 w-64" />
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
        <Skeleton className="h-24" />
      </div>
      <Skeleton className="h-72" />
    </div>
  )
}

function findFolderById(
  folder: FolderTreeNode | undefined,
  folderId: string
): FolderTreeNode | undefined {
  if (!folder) return undefined
  if (folder.id === folderId) return folder
  for (const child of folder.children) {
    const match = findFolderById(child, folderId)
    if (match) return match
  }
  return undefined
}

function findFolderAncestors(
  root: FolderTreeNode,
  folderId: string
): FolderTreeNode[] {
  if (root.id === folderId) return [root]
  for (const child of root.children) {
    const childPath = findFolderAncestors(child, folderId)
    if (childPath.length > 0) {
      return [root, ...childPath]
    }
  }
  return []
}

function getDisplayedAncestorIds(
  folder: FolderTreeNode | undefined,
  selectedFolderId: string
): Set<string> {
  if (!folder) return new Set()
  if (folder.id === selectedFolderId) return new Set([folder.id])
  for (const child of folder.children) {
    const ids = getDisplayedAncestorIds(child, selectedFolderId)
    if (ids.size > 0) {
      ids.add(folder.id)
      return ids
    }
  }
  return new Set()
}

function buildFolderRoute(folder: FolderTreeNode) {
  if (folder.parent_id === null) {
    return "/"
  }
  return `/folder/${encodeURIComponent(folder.id)}`
}

function formatDateTime(value: string | undefined) {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString()
}

function formatDetailValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—"
  if (typeof value === "string") return value
  if (typeof value === "number" || typeof value === "boolean") return String(value)
  return JSON.stringify(value)
}

function formatParseStatus(status: number) {
  switch (status) {
    case 1:
      return "Pending"
    case 2:
      return "Parsing"
    case 3:
      return "Ready"
    case 4:
      return "Failed"
    default:
      return "Unknown"
  }
}
