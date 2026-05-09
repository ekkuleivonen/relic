import * as React from "react"
import { useDraggable, useDroppable } from "@dnd-kit/core"
import { ChevronRight, Folder } from "lucide-react"
import { Link } from "react-router"

import { FolderContextMenu } from "@/components/filesystem/folder-context-menu"
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { DRAG_TYPE_FOLDER } from "@/hooks/use-folder-dnd"
import { useFolderDragState } from "@/hooks/use-folder-drag-state"
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
  const sortedChildren = React.useMemo(
    () => [...node.children].sort((a, b) => a.name.localeCompare(b.name)),
    [node.children]
  )
  const hasChildren = sortedChildren.length > 0
  const href = buildFolderHref(node.id, pathSegments)
  const isSelected = selectedFolderId === node.id

  const dragState = useFolderDragState()
  const isRoot = node.parent_id === null
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
    disabled: isInvalidTarget,
  })

  const setRefs = React.useCallback(
    (el: HTMLDivElement | null) => {
      draggable.setNodeRef(el)
      droppable.setNodeRef(el)
    },
    [draggable, droppable]
  )

  const rowContent = (
    <div
      ref={setRefs}
      {...draggable.listeners}
      {...draggable.attributes}
      className={cn(
        "flex items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        isSelected && "bg-muted text-foreground",
        droppable.isOver &&
          "bg-primary/10 ring-2 ring-inset ring-primary/40 text-foreground",
        draggable.isDragging && "opacity-40"
      )}
    >
      {hasChildren ? (
        <CollapsibleTrigger className="flex size-7 items-center justify-center rounded-md">
          <ChevronRight className="size-4 transition-transform data-[state=open]:rotate-90" />
          <span className="sr-only">Toggle {node.name || "root"}</span>
        </CollapsibleTrigger>
      ) : (
        <span className="size-7" />
      )}
      <Link
        to={href}
        className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-2"
        draggable={false}
        onClick={(event) => {
          if (draggable.isDragging) {
            event.preventDefault()
          }
        }}
      >
        <Folder className="size-4 shrink-0" />
        <span className="truncate">{getNodeLabel(node, pathSegments)}</span>
      </Link>
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
    <Collapsible defaultOpen={expandedFolderIds.has(node.id)}>
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

  return `/f/${encodeURIComponent(folderId)}`
}
