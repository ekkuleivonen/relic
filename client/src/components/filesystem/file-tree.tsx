import * as React from "react"
import { ChevronRight, Folder } from "lucide-react"
import { Link } from "react-router"

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
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

  if (!hasChildren) {
    return (
      <Link
        to={href}
        className={cn(
          "flex items-center gap-2 rounded-md px-2 py-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
          isSelected && "bg-muted text-foreground"
        )}
      >
        <span className="size-4" />
        <Folder className="size-4" />
        <span className="truncate">{getNodeLabel(node, pathSegments)}</span>
      </Link>
    )
  }

  return (
    <Collapsible defaultOpen={expandedFolderIds.has(node.id)}>
      <div
        className={cn(
          "flex items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
          isSelected && "bg-muted text-foreground"
        )}
      >
        <CollapsibleTrigger className="flex size-7 items-center justify-center rounded-md">
          <ChevronRight className="size-4 transition-transform data-[state=open]:rotate-90" />
          <span className="sr-only">Toggle {node.name || "root"}</span>
        </CollapsibleTrigger>
        <Link to={href} className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-2">
          <Folder className="size-4 shrink-0" />
          <span className="truncate">{getNodeLabel(node, pathSegments)}</span>
        </Link>
      </div>
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

