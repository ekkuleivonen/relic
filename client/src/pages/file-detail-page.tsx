import * as React from "react"
import {
  Download,
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
import { Input } from "@/components/ui/input"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { useFile, useDownloadFile, useRenameFile } from "@/hooks/use-files"
import { useFolderTree } from "@/hooks/use-filesystem"
import { extractApiError } from "@/lib/api"
import { formatBytes } from "@/lib/format"
import { PERM, can } from "@/lib/permissions"
import { buildSingleFilterHref } from "@/lib/search-query"
import { cn } from "@/lib/utils"
import type {
  FileMetaSection,
  FileSystemFile,
  FolderTreeNode,
} from "@/types/filesystem"

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
    <div className="h-svh overflow-hidden bg-background text-foreground">
      <div className="grid h-full min-h-0 lg:grid-cols-[20rem_1fr]">
        <aside className="flex min-h-0 flex-col overflow-hidden border-b bg-sidebar p-4 lg:border-r lg:border-b-0">
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

        <main className="min-h-0 min-w-0 overflow-y-auto p-4 lg:p-8">
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
  const rename = useRenameFile()
  const canRename = Boolean(
    folder && can(folder.effective_permissions, PERM.WRITE)
  )
  const [titleEditing, setTitleEditing] = React.useState(false)
  const [titleDraft, setTitleDraft] = React.useState(file.name)
  const renameCommitRef = React.useRef(false)
  const kvEntries = Object.entries(file.meta.kvs)

  function beginTitleRename() {
    setTitleDraft(file.name)
    setTitleEditing(true)
  }

  async function commitTitleRename() {
    if (renameCommitRef.current) return
    const trimmed = titleDraft.trim()
    if (!trimmed) {
      setTitleDraft(file.name)
      setTitleEditing(false)
      return
    }
    if (trimmed === file.name) {
      setTitleEditing(false)
      return
    }
    renameCommitRef.current = true
    try {
      await rename.mutateAsync({ file_id: file.id, name: trimmed })
      setTitleEditing(false)
    } catch {
      setTitleDraft(file.name)
    } finally {
      renameCommitRef.current = false
    }
  }

  function cancelTitleRename() {
    setTitleDraft(file.name)
    setTitleEditing(false)
  }

  return (
    <>
      <FileBreadcrumbs root={root} folder={folder} file={file} />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <h1 className="min-w-0 w-full">
            {titleEditing ? (
              <Input
                value={titleDraft}
                onChange={(event) => setTitleDraft(event.target.value)}
                onBlur={() => void commitTitleRename()}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    event.preventDefault()
                    cancelTitleRename()
                  } else if (event.key === "Enter") {
                    event.preventDefault()
                    void commitTitleRename()
                  }
                }}
                disabled={rename.isPending}
                className="box-border block h-auto min-h-10 w-full min-w-0 border-0 border-b border-transparent bg-transparent px-0 py-1 text-2xl font-semibold leading-tight tracking-tight shadow-none rounded-none md:text-2xl md:leading-tight focus-visible:border-b focus-visible:border-foreground/40 focus-visible:ring-0 focus-visible:ring-offset-0 dark:bg-transparent"
                autoFocus
                onFocus={(event) => event.target.select()}
                aria-label="File name"
              />
            ) : canRename ? (
              <button
                type="button"
                className="truncate max-w-full text-2xl font-semibold tracking-tight text-left hover:underline decoration-transparent hover:decoration-foreground/40 underline-offset-4"
                title="Double-click to rename"
                onClick={(event) => {
                  if (event.detail >= 2) {
                    event.preventDefault()
                    beginTitleRename()
                  }
                }}
                onDoubleClick={(event) => {
                  event.preventDefault()
                  beginTitleRename()
                }}
              >
                {file.name}
              </button>
            ) : (
              <span className="truncate text-2xl font-semibold tracking-tight">
                {file.name}
              </span>
            )}
          </h1>
          {!folder ? (
            <p className="mt-1 text-sm text-muted-foreground">
              Folder unavailable
            </p>
          ) : null}
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
          value={formatFileInfoStatus(file.meta.sections?.file_info?.status)}
        />
        <StatCard label="Size" value={formatBytes(file.meta.size)} />
        <StatCard label="Type" value={file.meta.mimetype || "Unknown"} />
      </div>

      <Card>
        <CardHeader className="gap-2 sm:flex sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>File Metadata</CardTitle>
          <Badge variant="outline">schema {file.meta.schema_version}</Badge>
        </CardHeader>
        <CardContent className="space-y-4">
          <DetailGrid
            rows={[
              { label: "File ID", value: file.id },
              { label: "Blob ID", value: file.blob_id },
              {
                label: "Uploaded by",
                value: file.uploaded_by_name ?? file.uploaded_by,
                href: buildSingleFilterHref({
                  uploaded_by: file.uploaded_by,
                }),
                hint: "Find files uploaded by this user",
              },
              {
                label: "Original filename",
                value: file.meta.original_filename ?? file.name,
              },
              {
                label: "Extension",
                value: file.meta.extension || "—",
                href: file.meta.extension
                  ? buildSingleFilterHref({
                      extensions: [file.meta.extension],
                    })
                  : undefined,
                hint: "Find files with this extension",
              },
              {
                label: "MIME type",
                value: file.meta.mimetype || "—",
                href: file.meta.mimetype
                  ? buildSingleFilterHref({
                      mimetypes: [file.meta.mimetype],
                    })
                  : undefined,
                hint: "Find files with this MIME type",
              },
              { label: "Size", value: formatBytes(file.meta.size) },
              { label: "Summary", value: file.meta.summary || "—" },
              { label: "Created", value: formatDateTime(file.created_at) },
              { label: "Updated", value: formatDateTime(file.updated_at) },
            ]}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-2 sm:flex sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Tags & Keywords</CardTitle>
          <Badge variant="outline">
            {file.meta.tags.length + file.meta.keywords.length} terms
          </Badge>
        </CardHeader>
        <CardContent className="space-y-5">
          <TokenGroup
            label="Tags"
            values={file.meta.tags}
            tone="tag"
            buildHref={(value) =>
              buildSingleFilterHref({ tags: [value] })
            }
            hint="Find files tagged"
          />
          <TokenGroup
            label="Keywords"
            values={file.meta.keywords}
            tone="keyword"
            buildHref={(value) =>
              buildSingleFilterHref({ keywords: [value] })
            }
            hint="Find files with keyword"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="gap-2 sm:flex sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Key Values</CardTitle>
          <Badge variant="outline">{kvEntries.length} fields</Badge>
        </CardHeader>
        <CardContent>
          {kvEntries.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No key/value metadata is attached to this file.
            </p>
          ) : (
            <KeyValueCollection entries={kvEntries} />
          )}
        </CardContent>
      </Card>

      <ProcessorSectionsCard sections={file.meta.sections ?? {}} />
    </>
  )
}

function ProcessorSectionsCard({
  sections,
}: {
  sections: Record<string, FileMetaSection>
}) {
  const kinds = Object.keys(sections).sort()
  return (
    <Card>
      <CardHeader className="gap-2 sm:flex sm:flex-row sm:items-center sm:justify-between">
        <CardTitle>Processor Sections</CardTitle>
        <Badge variant="outline">{kinds.length} sections</Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {kinds.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No processor has written a section for this file yet.
          </p>
        ) : (
          kinds.map((kind) => (
            <ProcessorSectionRow key={kind} kind={kind} section={sections[kind]} />
          ))
        )}
      </CardContent>
    </Card>
  )
}

function ProcessorSectionRow({
  kind,
  section,
}: {
  kind: string
  section: FileMetaSection
}) {
  const kvEntries = Object.entries(section.kvs ?? {})
  return (
    <div className="rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{kind}</span>
        <Badge variant="outline" className="capitalize">
          {section.status}
        </Badge>
        {section.extracted_at && (
          <span className="text-xs text-muted-foreground">
            {formatDateTime(section.extracted_at)}
          </span>
        )}
      </div>
      {section.summary && (
        <p className="mt-2 text-sm text-muted-foreground">{section.summary}</p>
      )}
      {(section.tags?.length || section.keywords?.length) ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {section.tags?.map((tag) => (
            <Badge key={`tag-${tag}`} variant="secondary">
              {tag}
            </Badge>
          ))}
          {section.keywords?.map((keyword) => (
            <Badge key={`kw-${keyword}`} variant="outline">
              {keyword}
            </Badge>
          ))}
        </div>
      ) : null}
      {kvEntries.length > 0 && (
        <dl className="mt-3 grid gap-1 text-sm sm:grid-cols-[10rem_1fr]">
          {kvEntries.map(([key, value]) => (
            <React.Fragment key={key}>
              <dt className="text-muted-foreground">{key}</dt>
              <dd className="break-all font-mono text-xs">
                {value === null ? "—" : String(value)}
              </dd>
            </React.Fragment>
          ))}
        </dl>
      )}
      {section.error_message && (
        <p className="mt-2 text-sm text-destructive">
          {section.error_class}: {section.error_message}
        </p>
      )}
    </div>
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

type DetailRow = {
  label: string
  value: unknown
  href?: string
  hint?: string
}

function DetailGrid({ rows }: { rows: DetailRow[] }) {
  return (
    <dl className="grid gap-3 text-sm sm:grid-cols-[10rem_1fr]">
      {rows.map((row) => (
        <React.Fragment key={row.label}>
          <dt className="text-muted-foreground">{row.label}</dt>
          <dd className="break-all text-sm">
            {row.href ? (
              <Link
                to={row.href}
                title={row.hint}
                className="hover:underline"
              >
                {formatDetailValue(row.value)}
              </Link>
            ) : (
              formatDetailValue(row.value)
            )}
          </dd>
        </React.Fragment>
      ))}
    </dl>
  )
}

function TokenGroup({
  label,
  values,
  tone,
  buildHref,
  hint,
}: {
  label: string
  values: string[]
  tone: "tag" | "keyword"
  buildHref?: (value: string) => string
  hint?: string
}) {
  return (
    <section>
      <h3 className="mb-3 text-sm font-medium">{label}</h3>
      {values.length === 0 ? (
        <p className="text-sm text-muted-foreground">None yet.</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {values.map((value) => {
            const className = cn(
              "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
              tone === "tag"
                ? "border-primary/20 bg-primary/10 text-primary"
                : "border-muted-foreground/20 bg-muted text-muted-foreground",
              buildHref && "hover:border-primary/40 hover:text-primary"
            )
            if (buildHref) {
              return (
                <Link
                  key={value}
                  to={buildHref(value)}
                  className={className}
                  title={hint ? `${hint} ${value}` : undefined}
                >
                  {value}
                </Link>
              )
            }
            return (
              <div key={value} className={className}>
                {value}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

function KeyValueCollection({
  entries,
}: {
  entries: Array<[string, string | number | boolean | null]>
}) {
  return (
    <div className="divide-y rounded-md border">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className="grid gap-1 px-3 py-2 text-sm sm:grid-cols-[12rem_1fr] sm:gap-4"
        >
          <div className="font-medium text-muted-foreground">{key}</div>
          <div className="break-words font-mono text-xs">
            {formatDetailValue(value)}
          </div>
        </div>
      ))}
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

function formatFileInfoStatus(status: string | undefined) {
  switch (status) {
    case "pending":
      return "Pending"
    case "in_progress":
      return "Extracting"
    case "completed":
      return "Ready"
    case "failed":
      return "Failed"
    case "skipped":
      return "Skipped"
    default:
      return "Unknown"
  }
}
