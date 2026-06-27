import * as React from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  type User,
  type UserCreateInput,
  type UserRole,
  userRoles,
} from "@/types/auth"

type UserFormProps = {
  user?: User
  submitLabel: string
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (values: UserCreateInput) => Promise<void>
}

export function UserForm({
  user,
  submitLabel,
  isSubmitting,
  onCancel,
  onSubmit,
}: UserFormProps) {
  const [email, setEmail] = React.useState(user?.email ?? "")
  const [displayName, setDisplayName] = React.useState(user?.display_name ?? "")
  const [password, setPassword] = React.useState("")
  const [role, setRole] = React.useState<UserRole>(user?.role ?? "user")
  const isEdit = user !== undefined

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await onSubmit({
      email,
      display_name: displayName,
      password: password || undefined,
      role,
    })
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="grid gap-2">
        <Label htmlFor="user-display-name">Display name</Label>
        <Input
          id="user-display-name"
          placeholder="Ada Lovelace"
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="user-email">Email</Label>
        <Input
          id="user-email"
          type="email"
          placeholder="ada@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          disabled={isEdit}
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="user-password">
          {isEdit ? "New password" : "Initial password"}
        </Label>
        <Input
          id="user-password"
          type="password"
          placeholder={isEdit ? "Leave blank to keep current password" : "Optional"}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </div>

      <div className="grid gap-2">
        <Label>Role</Label>
        <Select value={role} onValueChange={(value) => setRole(value as UserRole)}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select role" />
          </SelectTrigger>
          <SelectContent>
            {userRoles.map((item) => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving..." : submitLabel}
        </Button>
      </div>
    </form>
  )
}
