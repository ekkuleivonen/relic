import type { User } from "@/types/users"

export const Permission = {
  READ: 1,
  WRITE: 2,
  DELETE: 4,
  ENRICH: 8,
} as const

export type PermissionBit = (typeof Permission)[keyof typeof Permission]

export const PERMISSION_OPTIONS: ReadonlyArray<{
  bit: PermissionBit
  letter: string
  label: string
  description: string
}> = [
  { bit: Permission.READ, letter: "R", label: "Read", description: "List folders and download files." },
  { bit: Permission.WRITE, letter: "W", label: "Write", description: "Upload and overwrite files." },
  { bit: Permission.DELETE, letter: "D", label: "Delete", description: "Remove files and folders." },
  {
    bit: Permission.ENRICH,
    letter: "E",
    label: "Enrich",
    description: "Update file metadata (used by processors and substrates).",
  },
]

export type FolderAccess = {
  id: string
  user: User
  folder_id: string
  folder_path: string
  permissions: number
  created_at: string
  updated_at: string
}

export type FolderAccessGrantInput = {
  user_id: string
  folder_id: string
  permissions: number
}
