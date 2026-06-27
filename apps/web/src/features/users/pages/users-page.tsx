import * as React from "react"
import { useSearchParams } from "react-router"

import { PageShell } from "@/components/page-shell"
import { UserForm } from "@/features/users/components/user-form"
import { UsersTable } from "@/features/users/components/users-table"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useCreateUser, useUpdateUser, useUsers } from "@/hooks/use-users"
import type { User, UserCreateInput, UserUpdateInput } from "@/types/auth"

export function UsersPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const usersQuery = useUsers()
  const createUser = useCreateUser()
  const updateUser = useUpdateUser()

  const [isCreateOpen, setIsCreateOpen] = React.useState(false)
  const [editingUser, setEditingUser] = React.useState<User | null>(null)

  React.useEffect(() => {
    const editUserId = searchParams.get("edit")
    if (!editUserId || !usersQuery.data) {
      return
    }

    const user = usersQuery.data.find((entry) => entry.id === editUserId)
    if (!user) {
      return
    }

    setEditingUser(user)
    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete("edit")
    setSearchParams(nextParams, { replace: true })
  }, [searchParams, setSearchParams, usersQuery.data])

  async function handleCreate(values: UserCreateInput) {
    await createUser.mutateAsync(values)
    setIsCreateOpen(false)
  }

  async function handleUpdate(values: UserCreateInput) {
    if (!editingUser) {
      return
    }

    const input: UserUpdateInput = {
      display_name: values.display_name,
      role: values.role,
    }
    if (values.password) {
      input.password = values.password
    }

    await updateUser.mutateAsync({
      userId: editingUser.id,
      input,
    })
    setEditingUser(null)
  }

  async function handleToggleDisabled(user: User) {
    await updateUser.mutateAsync({
      userId: user.id,
      input: { disabled: !user.disabled_at },
    })
  }

  return (
    <PageShell>
      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
          <p className="mt-4 max-w-2xl text-sm/7 text-muted-foreground">
            Manage accounts, roles, and access for this Relic instance.
          </p>
        </div>
        <Button type="button" onClick={() => setIsCreateOpen(true)}>
          Add user
        </Button>
      </header>

      <section className="mt-8">
        <Card>
          <CardHeader>
            <CardTitle>User accounts</CardTitle>
          </CardHeader>
          <CardContent>
            <UsersTable
              users={usersQuery.data ?? []}
              isLoading={usersQuery.isLoading}
              onEdit={setEditingUser}
              onToggleDisabled={handleToggleDisabled}
            />
          </CardContent>
        </Card>
      </section>

      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add user</DialogTitle>
            <DialogDescription>
              Create a provisioned account. Users can sign in with password and/or SSO once created.
            </DialogDescription>
          </DialogHeader>
          <UserForm
            submitLabel="Create user"
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
            <DialogTitle>Edit user</DialogTitle>
            <DialogDescription>
              Leave password blank unless you want to reset it.
            </DialogDescription>
          </DialogHeader>
          {editingUser ? (
            <UserForm
              key={editingUser.id}
              user={editingUser}
              submitLabel="Save changes"
              isSubmitting={updateUser.isPending}
              onCancel={() => setEditingUser(null)}
              onSubmit={handleUpdate}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </PageShell>
  )
}
