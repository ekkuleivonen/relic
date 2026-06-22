export const PERM = {
  READ: 1,
  WRITE: 2,
  DELETE: 4,
  ENRICH: 8,
} as const

export type PermissionBit = (typeof PERM)[keyof typeof PERM]

export function can(effective: number, bit: PermissionBit): boolean {
  return (effective & bit) === bit
}

type FolderPermissionTarget = {
  parent_id: string | null
  effective_permissions: number
}

export function isRootFolder(folder: { parent_id: string | null }): boolean {
  return folder.parent_id === null
}

/** Root is structural only — files must live in a subfolder. */
export function canAcceptFiles(folder: FolderPermissionTarget): boolean {
  return !isRootFolder(folder) && can(folder.effective_permissions, PERM.WRITE)
}
