import * as React from "react"

import { UserForm } from "@/components/users/user-form"
import { UsersTable } from "@/components/users/users-table"
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
import {
  useCreateUser,
  useDeleteUser,
  useUpdateUser,
  useUsers,
} from "@/hooks/use-users"
import type { User, UserCreateInput, UserUpdateInput } from "@/types/users"

export function UsersPage() {
  const usersQuery = useUsers()
  const createUser = useCreateUser()
  const updateUser = useUpdateUser()
  const deleteUser = useDeleteUser()

  const [isCreateOpen, setIsCreateOpen] = React.useState(false)
  const [editingUser, setEditingUser] = React.useState<User | null>(null)
  const [deletingUser, setDeletingUser] = React.useState<User | null>(null)

  async function handleCreate(values: UserCreateInput) {
    await createUser.mutateAsync(values)
    setIsCreateOpen(false)
  }

  async function handleUpdate(values: UserCreateInput) {
    if (!editingUser) {
      return
    }

    const input: UserUpdateInput = {
      name: values.name,
      email: values.email,
      role: values.role,
    }

    if (values.password.length > 0) {
      input.password = values.password
    }

    await updateUser.mutateAsync({
      userId: editingUser.id,
      input,
    })
    setEditingUser(null)
  }

  async function handleDelete() {
    if (!deletingUser) {
      return
    }

    await deleteUser.mutateAsync(deletingUser.id)
    setDeletingUser(null)
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
          <p className="text-sm text-muted-foreground">
            Manage internal users, roles, and password resets.
          </p>
        </div>
        <Button type="button" onClick={() => setIsCreateOpen(true)}>
          Add User
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>User Accounts</CardTitle>
        </CardHeader>
        <CardContent>
          <UsersTable
            users={usersQuery.data ?? []}
            isLoading={usersQuery.isLoading}
            onEdit={setEditingUser}
            onDelete={setDeletingUser}
          />
        </CardContent>
      </Card>

      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add User</DialogTitle>
            <DialogDescription>
              Create an internal account. Session enforcement will be wired in
              after this admin surface.
            </DialogDescription>
          </DialogHeader>
          <UserForm
            submitLabel="Create User"
            isSubmitting={createUser.isPending}
            onCancel={() => setIsCreateOpen(false)}
            onSubmit={handleCreate}
          />
        </DialogContent>
      </Dialog>

      <Dialog
        open={editingUser !== null}
        onOpenChange={(open) => {
          if (!open) {
            setEditingUser(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit User</DialogTitle>
            <DialogDescription>
              Leave password blank unless you want to reset it.
            </DialogDescription>
          </DialogHeader>
          {editingUser && (
            <UserForm
              key={editingUser.id}
              user={editingUser}
              submitLabel="Save Changes"
              isSubmitting={updateUser.isPending}
              onCancel={() => setEditingUser(null)}
              onSubmit={handleUpdate}
            />
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={deletingUser !== null}
        onOpenChange={(open) => {
          if (!open) {
            setDeletingUser(null)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete user?</AlertDialogTitle>
            <AlertDialogDescription>
              {deletingUser
                ? `This will delete ${deletingUser.name} and cascade related access keys and folder access grants. Users with uploaded files cannot be deleted.`
                : "This will delete the selected user."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={(event) => {
                event.preventDefault()
                void handleDelete()
              }}
              disabled={deleteUser.isPending}
            >
              {deleteUser.isPending ? "Deleting..." : "Delete"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
