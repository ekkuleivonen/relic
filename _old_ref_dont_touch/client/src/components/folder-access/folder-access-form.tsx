import * as React from "react"

import { FolderCombobox } from "@/components/folder-access/folder-combobox"
import { PermissionPicker } from "@/components/folder-access/permission-picker"
import { UserCombobox } from "@/components/folder-access/user-combobox"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import type { FolderPathEntry } from "@/lib/folder-path"
import {
  type FolderAccess,
  type FolderAccessGrantInput,
  Permission,
} from "@/types/folder-access"
import type { User } from "@/types/users"

type FolderAccessFormProps = {
  users: User[]
  folders: FolderPathEntry[]
  existingGrants: FolderAccess[]
  initial?: FolderAccess
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (input: FolderAccessGrantInput) => Promise<void>
}

export function FolderAccessForm({
  users,
  folders,
  existingGrants,
  initial,
  isSubmitting,
  onCancel,
  onSubmit,
}: FolderAccessFormProps) {
  const isEdit = initial !== undefined
  const [userId, setUserId] = React.useState(initial?.user.id ?? "")
  const [folderId, setFolderId] = React.useState(initial?.folder_id ?? "")
  const [permissions, setPermissions] = React.useState(
    initial?.permissions ?? Permission.READ
  )

  const ancestorWarning = useAncestorWarning({
    userId,
    folderId,
    folders,
    grants: existingGrants,
    excludeAccessId: initial?.id,
  })

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!userId || !folderId || permissions <= 0) {
      return
    }

    await onSubmit({
      actor_id: userId,
      folder_id: folderId,
      permissions,
    })
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="grid gap-2">
        <Label>User</Label>
        <UserCombobox
          users={users}
          value={userId || undefined}
          onChange={setUserId}
          disabled={isEdit}
        />
      </div>

      <div className="grid gap-2">
        <Label>Folder</Label>
        <FolderCombobox
          folders={folders}
          value={folderId || undefined}
          onChange={(id) => setFolderId(id ?? "")}
          disabled={isEdit}
        />
      </div>

      <PermissionPicker value={permissions} onChange={setPermissions} />

      {ancestorWarning && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-300">
          {ancestorWarning}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          type="submit"
          disabled={isSubmitting || !userId || !folderId || permissions <= 0}
        >
          {isSubmitting ? "Saving..." : isEdit ? "Save Changes" : "Grant Access"}
        </Button>
      </div>
    </form>
  )
}

type AncestorWarningArgs = {
  userId: string
  folderId: string
  folders: FolderPathEntry[]
  grants: FolderAccess[]
  excludeAccessId: string | undefined
}

function useAncestorWarning({
  userId,
  folderId,
  folders,
  grants,
  excludeAccessId,
}: AncestorWarningArgs): string | null {
  return React.useMemo(() => {
    if (!userId || !folderId) {
      return null
    }

    const target = folders.find((folder) => folder.id === folderId)
    if (!target) {
      return null
    }

    const userGrants = grants.filter(
      (grant) =>
        grant.user.id === userId &&
        grant.id !== excludeAccessId &&
        grant.folder_id !== folderId
    )

    const ancestor = userGrants.find((grant) =>
      isAncestorPath(grant.folder_path, target.path)
    )
    if (!ancestor) {
      return null
    }

    return `This user already has a grant on ${ancestor.folder_path}, which already covers this folder. Adding a grant here only makes sense if you plan to remove the ancestor grant.`
  }, [userId, folderId, folders, grants, excludeAccessId])
}

function isAncestorPath(ancestor: string, descendant: string): boolean {
  if (ancestor === descendant) {
    return false
  }
  if (ancestor === "/") {
    return true
  }
  return descendant.startsWith(`${ancestor}/`)
}
