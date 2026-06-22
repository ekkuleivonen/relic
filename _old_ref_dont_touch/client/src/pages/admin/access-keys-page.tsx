import * as React from "react"

import { AccessKeyCreateDialog } from "@/components/access-keys/access-key-create-dialog"
import { AccessKeysTable } from "@/components/access-keys/access-keys-table"
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
import { Input } from "@/components/ui/input"
import {
  useAccessKeys,
  useCreateAccessKey,
  useRevokeAccessKey,
} from "@/hooks/use-access-keys"
import { useUsers } from "@/hooks/use-users"
import type {
  AccessKey,
  AccessKeyCreateInput,
  CreatedAccessKey,
} from "@/types/access-keys"

export function AccessKeysPage() {
  const accessKeysQuery = useAccessKeys()
  const usersQuery = useUsers()
  const createAccessKey = useCreateAccessKey()
  const revokeAccessKey = useRevokeAccessKey()

  const [search, setSearch] = React.useState("")
  const [isCreateOpen, setIsCreateOpen] = React.useState(false)
  const [createdAccessKey, setCreatedAccessKey] =
    React.useState<CreatedAccessKey | null>(null)
  const [revoking, setRevoking] = React.useState<AccessKey | null>(null)

  const accessKeys = React.useMemo(
    () => accessKeysQuery.data ?? [],
    [accessKeysQuery.data]
  )
  const filteredAccessKeys = React.useMemo(
    () => filterAccessKeys(accessKeys, search),
    [accessKeys, search]
  )

  async function handleCreate(input: AccessKeyCreateInput) {
    const created = await createAccessKey.mutateAsync(input)
    setCreatedAccessKey(created)
  }

  async function handleRevoke() {
    if (!revoking) {
      return
    }

    await revokeAccessKey.mutateAsync(revoking.key_id)
    setRevoking(null)
  }

  function handleCreateOpenChange(open: boolean) {
    setIsCreateOpen(open)
    if (!open) {
      setCreatedAccessKey(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Access Keys</h1>
          <p className="text-sm text-muted-foreground">
            Mint and revoke access keys for users. Keys authenticate the JSON API
            (Bearer token) and the S3 gateway (SigV4).
          </p>
        </div>
        <Button type="button" onClick={() => setIsCreateOpen(true)}>
          Add Access Key
        </Button>
      </div>

      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle>Keys</CardTitle>
          <Input
            placeholder="Filter by user, email, name, or key id..."
            className="w-full sm:max-w-xs"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </CardHeader>
        <CardContent>
          <AccessKeysTable
            accessKeys={filteredAccessKeys}
            isLoading={accessKeysQuery.isLoading}
            revokingKeyId={revokeAccessKey.variables}
            onRevoke={setRevoking}
          />
        </CardContent>
      </Card>

      <AccessKeyCreateDialog
        open={isCreateOpen}
        users={usersQuery.data ?? []}
        isSubmitting={createAccessKey.isPending}
        createdAccessKey={createdAccessKey}
        onOpenChange={handleCreateOpenChange}
        onSubmit={handleCreate}
      />

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
            <AlertDialogTitle>Revoke access key?</AlertDialogTitle>
            <AlertDialogDescription>
              {revoking
                ? `This will revoke ${revoking.name} for ${revoking.user.name}. Existing requests signed with this key will stop working.`
                : "This will revoke the selected access key."}
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
              disabled={revokeAccessKey.isPending}
            >
              {revokeAccessKey.isPending ? "Revoking..." : "Revoke"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function filterAccessKeys(accessKeys: AccessKey[], search: string): AccessKey[] {
  const trimmed = search.trim().toLowerCase()
  if (!trimmed) {
    return accessKeys
  }

  return accessKeys.filter((accessKey) => {
    return (
      accessKey.name.toLowerCase().includes(trimmed) ||
      accessKey.key_id.toLowerCase().includes(trimmed) ||
      accessKey.user.name.toLowerCase().includes(trimmed) ||
      accessKey.user.email.toLowerCase().includes(trimmed)
    )
  })
}
