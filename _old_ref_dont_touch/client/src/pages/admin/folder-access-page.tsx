import * as React from "react"

import { FolderAccessForm } from "@/components/folder-access/folder-access-form"
import { FolderAccessTable } from "@/components/folder-access/folder-access-table"
import { PermissionBadges } from "@/components/folder-access/permission-badges"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { useFolderTree } from "@/hooks/use-filesystem"
import {
  useFolderAccess,
  useGrantFolderAccess,
  useRevokeFolderAccess,
} from "@/hooks/use-folder-access"
import { useUsers } from "@/hooks/use-users"
import { flattenFolderTree } from "@/lib/folder-path"
import type {
  FolderAccess,
  FolderAccessGrantInput,
} from "@/types/folder-access"

export function FolderAccessPage() {
  const accessQuery = useFolderAccess()
  const usersQuery = useUsers()
  const treeQuery = useFolderTree()
  const grant = useGrantFolderAccess()
  const revoke = useRevokeFolderAccess()

  const [search, setSearch] = React.useState("")
  const [isCreateOpen, setIsCreateOpen] = React.useState(false)
  const [editing, setEditing] = React.useState<FolderAccess | null>(null)
  const [revoking, setRevoking] = React.useState<FolderAccess | null>(null)

  const folders = React.useMemo(
    () => (treeQuery.data ? flattenFolderTree(treeQuery.data) : []),
    [treeQuery.data]
  )

  const grants = React.useMemo(
    () => accessQuery.data ?? [],
    [accessQuery.data]
  )
  const filteredGrants = React.useMemo(
    () => filterGrants(grants, search),
    [grants, search]
  )

  async function handleCreate(input: FolderAccessGrantInput) {
    await grant.mutateAsync(input)
    setIsCreateOpen(false)
  }

  async function handleUpdate(input: FolderAccessGrantInput) {
    if (!editing) {
      return
    }

    await grant.mutateAsync(input)
    setEditing(null)
  }

  async function handleRevoke() {
    if (!revoking) {
      return
    }

    await revoke.mutateAsync(revoking.id)
    setRevoking(null)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Folder Access
          </h1>
          <p className="text-sm text-muted-foreground">
            Grant users permissions on folders. Each grant applies recursively
            to descendant folders.
          </p>
        </div>
        <Button type="button" onClick={() => setIsCreateOpen(true)}>
          Add Grant
        </Button>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Grants</CardTitle>
          <Input
            placeholder="Filter by user, email, or folder path..."
            className="w-full sm:max-w-xs"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </CardHeader>
        <CardContent>
          <FolderAccessTable
            grants={filteredGrants}
            isLoading={accessQuery.isLoading}
            onEdit={setEditing}
            onRevoke={setRevoking}
          />
        </CardContent>
      </Card>

      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Add Folder Access</DialogTitle>
            <DialogDescription>
              Choose a user, a folder, and which permissions to grant. The
              grant applies recursively to descendant folders.
            </DialogDescription>
          </DialogHeader>
          <FolderAccessForm
            users={usersQuery.data ?? []}
            folders={folders}
            existingGrants={grants}
            isSubmitting={grant.isPending}
            onCancel={() => setIsCreateOpen(false)}
            onSubmit={handleCreate}
          />
        </DialogContent>
      </Dialog>

      <Dialog
        open={editing !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditing(null)
          }
        }}
      >
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Edit Folder Access</DialogTitle>
            <DialogDescription>
              Adjust permissions for this grant. To grant access to a different
              folder or user, revoke this grant and create a new one.
            </DialogDescription>
          </DialogHeader>
          {editing && (
            <FolderAccessForm
              key={editing.id}
              users={usersQuery.data ?? []}
              folders={folders}
              existingGrants={grants}
              initial={editing}
              isSubmitting={grant.isPending}
              onCancel={() => setEditing(null)}
              onSubmit={handleUpdate}
            />
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={revoking !== null}
        onOpenChange={(open) => {
          if (!open) {
            setRevoking(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke this grant?</AlertDialogTitle>
            <AlertDialogDescription asChild>
              {revoking ? (
                <div className="space-y-3">
                  <div>
                    This removes{" "}
                    <span className="font-medium">{revoking.user.name}</span>'s
                    direct access to{" "}
                    <span className="font-mono">{revoking.folder_path}</span>.
                    Inherited permissions from ancestor folders remain in
                    effect.
                  </div>
                  <PermissionBadges permissions={revoking.permissions} />
                </div>
              ) : (
                <div>This will revoke the selected grant.</div>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={(event) => {
                event.preventDefault()
                void handleRevoke()
              }}
              disabled={revoke.isPending}
            >
              {revoke.isPending ? "Revoking..." : "Revoke"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function filterGrants(grants: FolderAccess[], search: string): FolderAccess[] {
  const trimmed = search.trim().toLowerCase()
  if (!trimmed) {
    return grants
  }

  return grants.filter((grant) => {
    return (
      grant.user.name.toLowerCase().includes(trimmed) ||
      grant.user.email.toLowerCase().includes(trimmed) ||
      grant.folder_path.toLowerCase().includes(trimmed)
    )
  })
}
