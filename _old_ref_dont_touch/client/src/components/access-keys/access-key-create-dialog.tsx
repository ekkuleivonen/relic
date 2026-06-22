import * as React from "react"
import { CheckIcon, CopyIcon } from "lucide-react"
import { toast } from "sonner"

import { UserCombobox } from "@/components/folder-access/user-combobox"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type {
  AccessKeyCreateInput,
  CreatedAccessKey,
} from "@/types/access-keys"
import type { User } from "@/types/users"

type AccessKeyCreateDialogProps = {
  open: boolean
  users: User[]
  isSubmitting: boolean
  createdAccessKey: CreatedAccessKey | null
  onOpenChange: (open: boolean) => void
  onSubmit: (input: AccessKeyCreateInput) => Promise<void>
}

export function AccessKeyCreateDialog({
  open,
  users,
  isSubmitting,
  createdAccessKey,
  onOpenChange,
  onSubmit,
}: AccessKeyCreateDialogProps) {
  const [userId, setUserId] = React.useState("")
  const [name, setName] = React.useState("")

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!userId || !name.trim()) {
      return
    }

    await onSubmit({
      actor_id: userId,
      name: name.trim(),
    })
  }

  function handleOpenChange(nextOpen: boolean) {
    if (!nextOpen) {
      setUserId("")
      setName("")
    }
    onOpenChange(nextOpen)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Create Access Key</DialogTitle>
          <DialogDescription>
            Pick the user this SigV4 key should authenticate as. The secret is
            shown only once after creation.
          </DialogDescription>
        </DialogHeader>

        {createdAccessKey ? (
          <CreatedKeyView accessKey={createdAccessKey} />
        ) : (
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="grid gap-2">
              <Label>User</Label>
              <UserCombobox
                users={users}
                value={userId || undefined}
                onChange={setUserId}
              />
            </div>

            <div className="grid gap-2">
              <Label htmlFor="access-key-name">Name</Label>
              <Input
                id="access-key-name"
                placeholder="DuckDB ingest"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
              />
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleOpenChange(false)}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={isSubmitting || !userId || !name.trim()}>
                {isSubmitting ? "Creating..." : "Create Key"}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

function CreatedKeyView({ accessKey }: { accessKey: CreatedAccessKey }) {
  return (
    <div className="space-y-4">
      <div className="rounded-md border border-amber-500/40 bg-amber-500/5 p-3 text-xs text-amber-700 dark:text-amber-300">
        Copy the secret now. It cannot be shown again after this dialog closes.
      </div>

      <CopyableValue label="Key ID" value={accessKey.key_id} />
      <CopyableValue label="Secret Access Key" value={accessKey.secret_access_key} />

      <DialogFooter showCloseButton />
    </div>
  )
}

function CopyableValue({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = React.useState(false)

  async function copyValue() {
    await navigator.clipboard.writeText(value)
    setCopied(true)
    toast.success(`${label} copied`)
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div className="grid gap-2">
      <Label>{label}</Label>
      <InputGroup className="h-9">
        <InputGroupInput value={value} readOnly className="font-mono text-xs" />
        <InputGroupAddon align="inline-end">
          <InputGroupButton
            type="button"
            size="icon-xs"
            aria-label={`Copy ${label}`}
            onClick={copyValue}
          >
            {copied ? <CheckIcon /> : <CopyIcon />}
          </InputGroupButton>
        </InputGroupAddon>
      </InputGroup>
    </div>
  )
}
