import * as React from "react"
import { useDraggable, useDroppable } from "@dnd-kit/core"
import { ChevronRight, Folder, FolderOpen } from "lucide-react"
import { useNavigate } from "react-router"

import { FolderContextMenu } from "@/components/filesystem/folder-context-menu"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { DRAG_TYPE_FOLDER } from "@/hooks/use-folder-dnd"
import { useFolderDragState } from "@/hooks/use-folder-drag-state"
import { useNativeFileDrop } from "@/hooks/use-native-file-drop"
import { useUpdateFolder } from "@/hooks/use-folders"
import { PERM, can, canAcceptFiles, isRootFolder } from "@/lib/permissions"
import { cn } from "@/lib/utils"
import type { FolderTreeNode } from "@/types/filesystem"

type FileTreeProps = {
  root: FolderTreeNode
  selectedFolderId: string | undefined
  expandedFolderIds: Set<string>
}

export function FileTree({
  root,
  selectedFolderId,
  expandedFolderIds,
}: FileTreeProps) {
  return (
    <nav aria-label="Filesystem" className="space-y-1 text-sm">
      <TreeNode
        node={root}
        pathSegments={[]}
        selectedFolderId={selectedFolderId}
        expandedFolderIds={expandedFolderIds}
      />
    </nav>
  )
}

type TreeNodeProps = {
  node: FolderTreeNode
  pathSegments: string[]
  selectedFolderId: string | undefined
  expandedFolderIds: Set<string>
}

function TreeNode({
  node,
  pathSegments,
  selectedFolderId,
  expandedFolderIds,
}: TreeNodeProps) {
  const navigate = useNavigate()
  const rename = useUpdateFolder()
  const sortedChildren = React.useMemo(
    () => [...node.children].sort((a, b) => a.name.localeCompare(b.name)),
    [node.children]
  )
  const hasChildren = sortedChildren.length > 0
  const href = buildFolderHref(node.id, pathSegments)
  const isSelected = selectedFolderId === node.id
  const [open, setOpen] = React.useState(expandedFolderIds.has(node.id))

  const dragState = useFolderDragState()
  const isRoot = isRootFolder(node)
  const canWriteHere = can(node.effective_permissions, PERM.WRITE)
  const acceptsFiles = canAcceptFiles(node)
  const canRename = !isRoot && canWriteHere
  const [editing, setEditing] = React.useState(false)
  const [draftName, setDraftName] = React.useState(node.name)
  const navTimerRef = React.useRef<number | null>(null)
  const renameCommitRef = React.useRef(false)
  const draggable = useDraggable({
    id: `tree-folder:${node.id}`,
    data: { type: DRAG_TYPE_FOLDER, folder: node },
    disabled: isRoot,
  })
  const isInvalidTarget =
    dragState.activeFolder !== null &&
    dragState.invalidTargetIds.has(node.id)
  const droppable = useDroppable({
    id: `tree-folder-drop:${node.id}`,
    data: { type: DRAG_TYPE_FOLDER, folder: node },
    disabled: isInvalidTarget || !canWriteHere,
  })
  const nativeDrop = useNativeFileDrop({
    folderId: node.id,
    disabled: !acceptsFiles,
  })

  const setRefs = React.useCallback(
    (el: HTMLDivElement | null) => {
      draggable.setNodeRef(el)
      droppable.setNodeRef(el)
    },
    [draggable, droppable]
  )

  const showHighlight = droppable.isOver || nativeDrop.isOver

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

  function scheduleOpenFolder() {
    if (draggable.isDragging) return
    clearNavTimer()
    navTimerRef.current = window.setTimeout(() => {
      navigate(href)
      navTimerRef.current = null
    }, 280)
  }

  async function commitRename() {
    if (renameCommitRef.current) return
    const trimmed = draftName.trim()
    if (!trimmed) {
      setDraftName(node.name)
      setEditing(false)
      return
    }
    if (trimmed === node.name) {
      setEditing(false)
      return
    }
    renameCommitRef.current = true
    try {
      await rename.mutateAsync({ id: node.id, name: trimmed })
      setEditing(false)
    } catch {
      setDraftName(node.name)
      // useUpdateFolder toasts the error
    } finally {
      renameCommitRef.current = false
    }
  }

  function cancelRename() {
    setDraftName(node.name)
    setEditing(false)
  }

  const rowContent = (
    <div
      ref={setRefs}
      {...draggable.listeners}
      {...draggable.attributes}
      {...nativeDrop.handlers}
      className={cn(
        "flex items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        isSelected && "bg-muted text-foreground",
        showHighlight &&
          "bg-primary/10 ring-2 ring-inset ring-primary/40 text-foreground",
        draggable.isDragging && "opacity-40"
      )}
    >
      {hasChildren ? (
        <CollapsibleTrigger className="flex size-7 items-center justify-center rounded-md">
          <ChevronRight
            className={cn("size-4 transition-transform", open && "rotate-90")}
          />
          <span className="sr-only">Toggle {node.name || "root"}</span>
        </CollapsibleTrigger>
      ) : (
        <span className="size-7" />
      )}
      {editing ? (
        <div className="flex min-w-0 flex-1 items-center gap-2 py-1 pr-2">
          <TreeFolderIcon open={open && hasChildren} />
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
            className="h-7 py-1 text-sm"
            autoFocus
            onFocus={(event) => event.target.select()}
            draggable={false}
            onClick={(event) => event.stopPropagation()}
            onPointerDown={(event) => event.stopPropagation()}
          />
        </div>
      ) : canRename ? (
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-2 text-left"
          draggable={false}
          onClick={(event) => {
            if (draggable.isDragging) {
              event.preventDefault()
              return
            }
            scheduleOpenFolder()
          }}
          onDoubleClick={(event) => {
            event.preventDefault()
            clearNavTimer()
            setDraftName(node.name)
            setEditing(true)
          }}
        >
          <TreeFolderIcon open={open && hasChildren} />
          <span className="truncate">{getNodeLabel(node, pathSegments)}</span>
        </button>
      ) : (
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-2 text-left"
          draggable={false}
          onClick={(event) => {
            if (draggable.isDragging) {
              event.preventDefault()
              return
            }
            navigate(href)
          }}
        >
          <TreeFolderIcon open={open && hasChildren} />
          <span className="truncate">{getNodeLabel(node, pathSegments)}</span>
        </button>
      )}
    </div>
  )

  const wrappedRow = (
    <FolderContextMenu folder={node} asChild>
      {rowContent}
    </FolderContextMenu>
  )

  if (!hasChildren) {
    return wrappedRow
  }

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      {wrappedRow}
      <CollapsibleContent className="ml-4 border-l pl-2">
        {sortedChildren.map((child) => (
          <TreeNode
            key={child.id}
            node={child}
            pathSegments={[...pathSegments, child.name]}
            selectedFolderId={selectedFolderId}
            expandedFolderIds={expandedFolderIds}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  )
}

function TreeFolderIcon({ open }: { open: boolean }) {
  const Icon = open ? FolderOpen : Folder
  return <Icon className="size-4 shrink-0" />
}

function getNodeLabel(node: FolderTreeNode, pathSegments: string[]) {
  if (pathSegments.length === 0) {
    return node.name || "Filesystem"
  }

  return node.name
}

function buildFolderHref(folderId: string, pathSegments: string[]) {
  if (pathSegments.length === 0) {
    return "/"
  }

  return `/folder/${encodeURIComponent(folderId)}`
}
