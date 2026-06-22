import type { FolderTreeNode } from "@/types/filesystem"

export type FolderPathEntry = {
  id: string
  name: string
  path: string
  parentPath: string
}

export function flattenFolderTree(root: FolderTreeNode): FolderPathEntry[] {
  const out: FolderPathEntry[] = []

  function walk(node: FolderTreeNode, parentPath: string) {
    const path = composePath(parentPath, node.name)
    out.push({ id: node.id, name: node.name, path, parentPath })

    for (const child of node.children) {
      walk(child, path)
    }
  }

  walk(root, "")
  return out
}

export function composePath(parentPath: string, name: string): string {
  if (name === "") {
    return "/"
  }

  if (parentPath === "" || parentPath === "/") {
    return `/${name}`
  }

  return `${parentPath}/${name}`
}
