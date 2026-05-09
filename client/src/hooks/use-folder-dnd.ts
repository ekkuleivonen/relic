import * as React from "react"
import {
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core"

import { useUpdateFolder } from "@/hooks/use-folders"
import type { FolderDragState } from "@/hooks/use-folder-drag-state"
import { PERM, can } from "@/lib/permissions"
import type { FolderTreeNode } from "@/types/filesystem"

export const DRAG_TYPE_FOLDER = "folder" as const

export type FolderDragData = {
  type: typeof DRAG_TYPE_FOLDER
  folder: FolderTreeNode
}

type UseFolderDndArgs = {
  /** The full tree, used to compute descendant ids of the active folder. */
  tree: FolderTreeNode | undefined
}

export function useFolderDnd({ tree }: UseFolderDndArgs) {
  const update = useUpdateFolder()
  const [activeFolder, setActiveFolder] = React.useState<FolderTreeNode | null>(
    null
  )

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 5 },
    }),
    useSensor(KeyboardSensor)
  )

  const invalidTargetIds = React.useMemo(() => {
    if (!activeFolder) {
      return new Set<string>()
    }
    const sourceInTree = tree ? findNode(tree, activeFolder.id) : activeFolder
    return sourceInTree
      ? collectSubtreeIds(sourceInTree)
      : new Set<string>([activeFolder.id])
  }, [activeFolder, tree])

  const dragState = React.useMemo<FolderDragState>(
    () => ({ activeFolder, invalidTargetIds }),
    [activeFolder, invalidTargetIds]
  )

  function onDragStart(event: DragStartEvent) {
    const data = event.active.data.current as FolderDragData | undefined
    if (data?.type === DRAG_TYPE_FOLDER) {
      setActiveFolder(data.folder)
    }
  }

  function onDragCancel() {
    setActiveFolder(null)
  }

  function onDragEnd(event: DragEndEvent) {
    const active = event.active.data.current as FolderDragData | undefined
    const over = event.over?.data.current as FolderDragData | undefined
    setActiveFolder(null)

    if (!active || active.type !== DRAG_TYPE_FOLDER) return
    if (!over || over.type !== DRAG_TYPE_FOLDER) return

    const source = active.folder
    const destination = over.folder
    if (!isMoveAllowed(source, destination, tree)) return
    if (source.parent_id === destination.id) return

    update.mutate({ id: source.id, parent_id: destination.id })
  }

  return {
    sensors,
    activeFolder,
    dragState,
    onDragStart,
    onDragCancel,
    onDragEnd,
  }
}

export function isMoveAllowed(
  source: FolderTreeNode,
  destination: FolderTreeNode,
  tree: FolderTreeNode | undefined
): boolean {
  if (source.parent_id === null) return false
  if (destination.id === source.id) return false
  if (!can(source.effective_permissions, PERM.WRITE)) return false
  if (!can(destination.effective_permissions, PERM.WRITE)) return false

  const sourceInTree = tree ? findNode(tree, source.id) : source
  const subtree = sourceInTree
    ? collectSubtreeIds(sourceInTree)
    : new Set<string>([source.id])
  if (subtree.has(destination.id)) return false

  return true
}

function collectSubtreeIds(folder: FolderTreeNode): Set<string> {
  const ids = new Set<string>()
  const queue: FolderTreeNode[] = [folder]
  while (queue.length > 0) {
    const current = queue.shift()!
    ids.add(current.id)
    queue.push(...current.children)
  }
  return ids
}

function findNode(
  root: FolderTreeNode,
  id: string
): FolderTreeNode | undefined {
  if (root.id === id) return root
  for (const child of root.children) {
    const match = findNode(child, id)
    if (match) return match
  }
  return undefined
}
