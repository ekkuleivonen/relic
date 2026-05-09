import * as React from "react"
import { useDraggable, useDroppable } from "@dnd-kit/core"
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  File as FileIcon,
  Folder as FolderIcon,
} from "lucide-react"
import { Link, useNavigate } from "react-router"

import { FileContextMenu } from "@/components/filesystem/file-context-menu"
import { FolderContextMenu } from "@/components/filesystem/folder-context-menu"
import { Input } from "@/components/ui/input"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { DRAG_TYPE_FILE } from "@/hooks/use-file-dnd"
import { useRenameFile } from "@/hooks/use-files"
import { useNativeFileDrop } from "@/hooks/use-native-file-drop"
import { DRAG_TYPE_FOLDER } from "@/hooks/use-folder-dnd"
import { useFolderDragState } from "@/hooks/use-folder-drag-state"
import { formatBytes, formatRelativeTime } from "@/lib/format"
import { PERM, can } from "@/lib/permissions"
import { cn } from "@/lib/utils"
import type { FileSystemEntry } from "@/types/filesystem"

export type SortKey = "name" | "type" | "size" | "updated"
export type SortDir = "asc" | "desc"
export type SortState = { key: SortKey; dir: SortDir }

type FolderEntriesTableProps = {
  entries: FileSystemEntry[]
  sort: SortState
  onSortChange: (next: SortState) => void
}

export function FolderEntriesTable({
  entries,
  sort,
  onSortChange,
}: FolderEntriesTableProps) {
  const sorted = React.useMemo(
    () => sortEntries(entries, sort),
    [entries, sort]
  )

  function toggle(key: SortKey) {
    if (sort.key !== key) {
      onSortChange({ key, dir: "asc" })
      return
    }
    onSortChange({ key, dir: sort.dir === "asc" ? "desc" : "asc" })
  }

  return (
    <div className="overflow-hidden rounded-md border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/30 hover:bg-muted/30">
            <TableHead className="w-10 pl-3" />
            <TableHead>
              <SortButton
                label="Name"
                sortKey="name"
                sort={sort}
                onClick={toggle}
              />
            </TableHead>
            <TableHead>
              <SortButton
                label="Type"
                sortKey="type"
                sort={sort}
                onClick={toggle}
              />
            </TableHead>
            <TableHead className="w-28 text-right">
              <SortButton
                label="Size"
                sortKey="size"
                sort={sort}
                onClick={toggle}
                align="right"
              />
            </TableHead>
            <TableHead className="w-32 text-right pr-3">
              <SortButton
                label="Updated"
                sortKey="updated"
                sort={sort}
                onClick={toggle}
                align="right"
              />
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((entry) =>
            entry.kind === "folder" ? (
              <FolderRow key={`folder-${entry.id}`} entry={entry} />
            ) : (
              <FileRow key={`blob-${entry.id}`} entry={entry} />
            )
          )}
        </TableBody>
      </Table>
    </div>
  )
}

type SortButtonProps = {
  label: string
  sortKey: SortKey
  sort: SortState
  onClick: (key: SortKey) => void
  align?: "left" | "right"
}

function SortButton({
  label,
  sortKey,
  sort,
  onClick,
  align = "left",
}: SortButtonProps) {
  const active = sort.key === sortKey
  const Icon = !active ? ArrowUpDown : sort.dir === "asc" ? ArrowUp : ArrowDown
  return (
    <button
      type="button"
      onClick={() => onClick(sortKey)}
      className={cn(
        "inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors",
        align === "right" && "ml-auto"
      )}
    >
      <span>{label}</span>
      <Icon
        className={cn(
          "size-3",
          active ? "text-foreground" : "text-muted-foreground/50"
        )}
      />
    </button>
  )
}

type FolderRowProps = {
  entry: Extract<FileSystemEntry, { kind: "folder" }>
}

function FolderRow({ entry }: FolderRowProps) {
  const dragState = useFolderDragState()
  const canWriteHere = can(entry.node.effective_permissions, PERM.WRITE)
  const draggable = useDraggable({
    id: `table-folder:${entry.id}`,
    data: { type: DRAG_TYPE_FOLDER, folder: entry.node },
  })
  const isInvalidTarget =
    dragState.activeFolder !== null &&
    dragState.invalidTargetIds.has(entry.id)
  const droppable = useDroppable({
    id: `table-folder-drop:${entry.id}`,
    data: { type: DRAG_TYPE_FOLDER, folder: entry.node },
    disabled: isInvalidTarget || !canWriteHere,
  })
  const nativeDrop = useNativeFileDrop({
    folderId: entry.id,
    disabled: !canWriteHere,
  })

  const setRefs = React.useCallback(
    (el: HTMLTableRowElement | null) => {
      draggable.setNodeRef(el)
      droppable.setNodeRef(el)
    },
    [draggable, droppable]
  )

  const childCount = entry.child_count
  const typeLabel = `${childCount} ${childCount === 1 ? "subfolder" : "subfolders"}`
  const showHighlight = droppable.isOver || nativeDrop.isOver

  return (
    <FolderContextMenu folder={entry.node} asChild>
      <TableRow
        ref={setRefs}
        {...draggable.listeners}
        {...draggable.attributes}
        {...nativeDrop.handlers}
        data-drop-active={showHighlight ? "true" : undefined}
        className={cn(
          "cursor-pointer",
          draggable.isDragging && "opacity-40",
          showHighlight && "bg-primary/10 ring-2 ring-inset ring-primary/40"
        )}
      >
        <TableCell className="pl-3">
          <RowIcon kind="folder" />
        </TableCell>
        <TableCell className="font-medium">
          <Link
            to={entry.href}
            className="hover:underline"
            onClick={(event) => {
              if (draggable.isDragging) {
                event.preventDefault()
              }
            }}
            draggable={false}
          >
            {entry.name}
          </Link>
        </TableCell>
        <TableCell className="text-muted-foreground">{typeLabel}</TableCell>
        <TableCell className="text-right text-muted-foreground">—</TableCell>
        <TableCell className="text-right text-muted-foreground pr-3">
          {formatRelativeTime(entry.updated_at)}
        </TableCell>
      </TableRow>
    </FolderContextMenu>
  )
}

type FileRowProps = {
  entry: Extract<FileSystemEntry, { kind: "blob" }>
}

const FILE_NAME_NAV_DELAY_MS = 280

function FileRow({ entry }: FileRowProps) {
  const navigate = useNavigate()
  const rename = useRenameFile()
  const canRename = can(entry.folder.effective_permissions, PERM.WRITE)
  const [editing, setEditing] = React.useState(false)
  const [draftName, setDraftName] = React.useState(entry.name)
  const navTimerRef = React.useRef<number | null>(null)
  const renameCommitRef = React.useRef(false)
  const draggable = useDraggable({
    id: `table-file:${entry.id}`,
    data: {
      type: DRAG_TYPE_FILE,
      file: {
        id: entry.id,
        folder_id: entry.file.folder_id,
        name: entry.name,
      },
    },
  })

  const setRowRef = React.useCallback(
    (el: HTMLTableRowElement | null) => {
      draggable.setNodeRef(el)
    },
    [draggable]
  )

  const setDragHandleRef = React.useCallback(
    (el: HTMLTableCellElement | null) => {
      draggable.setActivatorNodeRef(el)
    },
    [draggable]
  )

  React.useEffect(
    () => () => {
      if (navTimerRef.current != null) {
        window.clearTimeout(navTimerRef.current)
      }
    },
    []
  )

  function clearNavTimer() {
    if (navTimerRef.current != null) {
      window.clearTimeout(navTimerRef.current)
      navTimerRef.current = null
    }
  }

  function scheduleOpenFile() {
    if (draggable.isDragging) return
    clearNavTimer()
    navTimerRef.current = window.setTimeout(() => {
      navigate(`/file/${encodeURIComponent(entry.id)}`)
      navTimerRef.current = null
    }, FILE_NAME_NAV_DELAY_MS)
  }

  async function commitRename() {
    if (renameCommitRef.current) return
    const trimmed = draftName.trim()
    if (!trimmed) {
      setDraftName(entry.name)
      setEditing(false)
      return
    }
    if (trimmed === entry.name) {
      setEditing(false)
      return
    }
    renameCommitRef.current = true
    try {
      await rename.mutateAsync({ file_id: entry.id, name: trimmed })
      setEditing(false)
    } catch {
      setDraftName(entry.name)
      // useRenameFile toasts the error
    } finally {
      renameCommitRef.current = false
    }
  }

  function cancelRename() {
    setDraftName(entry.name)
    setEditing(false)
  }

  return (
    <FileContextMenu file={entry.file} folder={entry.folder} asChild>
      <TableRow
        ref={setRowRef}
        className={cn(draggable.isDragging && "opacity-40")}
      >
        <TableCell
          ref={setDragHandleRef}
          {...draggable.listeners}
          {...draggable.attributes}
          className={cn(
            "cursor-grab active:cursor-grabbing pl-3",
            draggable.isDragging && "cursor-grabbing"
          )}
        >
          <RowIcon kind="blob" />
        </TableCell>
        <TableCell className="font-medium">
          {editing ? (
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
              className="h-8 py-1"
              autoFocus
              onFocus={(e) => e.target.select()}
              draggable={false}
              onClick={(e) => e.stopPropagation()}
            />
          ) : canRename ? (
            <button
              type="button"
              className="hover:underline text-left"
              onClick={(event) => {
                if (draggable.isDragging) {
                  event.preventDefault()
                  return
                }
                scheduleOpenFile()
              }}
              onDoubleClick={(event) => {
                event.preventDefault()
                clearNavTimer()
                setDraftName(entry.name)
                setEditing(true)
              }}
            >
              {entry.name}
            </button>
          ) : (
            <Link
              to={`/file/${encodeURIComponent(entry.id)}`}
              className="hover:underline"
              onClick={(event) => {
                if (draggable.isDragging) {
                  event.preventDefault()
                }
              }}
              draggable={false}
            >
              {entry.name}
            </Link>
          )}
        </TableCell>
        <TableCell className="text-muted-foreground">
          {entry.mime_type || "application/octet-stream"}
        </TableCell>
        <TableCell className="text-right text-muted-foreground">
          {formatBytes(entry.size)}
        </TableCell>
        <TableCell className="text-right text-muted-foreground pr-3">
          {formatRelativeTime(entry.updated_at)}
        </TableCell>
      </TableRow>
    </FileContextMenu>
  )
}

function RowIcon({ kind }: { kind: "folder" | "blob" }) {
  const Icon = kind === "folder" ? FolderIcon : FileIcon
  return (
    <div className="flex size-7 items-center justify-center rounded-md bg-muted text-muted-foreground">
      <Icon className="size-3.5" />
    </div>
  )
}

function compareNumbers(a: number | undefined, b: number | undefined): number {
  if (a === undefined && b === undefined) return 0
  if (a === undefined) return -1
  if (b === undefined) return 1
  return a - b
}

function sortEntries(
  entries: FileSystemEntry[],
  sort: SortState
): FileSystemEntry[] {
  const dirMul = sort.dir === "asc" ? 1 : -1
  // Folders always grouped above files for "name" sort to feel filesystem-y.
  const grouped = sort.key === "name"
  const folders = entries.filter((entry) => entry.kind === "folder")
  const files = entries.filter((entry) => entry.kind === "blob")

  const sortBy = (a: FileSystemEntry, b: FileSystemEntry): number => {
    switch (sort.key) {
      case "name":
        return a.name.localeCompare(b.name) * dirMul
      case "type": {
        const aType =
          a.kind === "folder" ? "folder" : a.mime_type || "application/octet-stream"
        const bType =
          b.kind === "folder" ? "folder" : b.mime_type || "application/octet-stream"
        return aType.localeCompare(bType) * dirMul
      }
      case "size": {
        const aSize = a.kind === "folder" ? -1 : a.size
        const bSize = b.kind === "folder" ? -1 : b.size
        return compareNumbers(aSize, bSize) * dirMul
      }
      case "updated": {
        const aUpdated = a.updated_at ? Date.parse(a.updated_at) : undefined
        const bUpdated = b.updated_at ? Date.parse(b.updated_at) : undefined
        return compareNumbers(aUpdated, bUpdated) * dirMul
      }
    }
  }

  if (grouped) {
    return [...folders.sort(sortBy), ...files.sort(sortBy)]
  }
  return [...entries].sort(sortBy)
}

