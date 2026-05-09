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
import { type User, type UserCreateInput, type UserRole, userRoles } from "@/types/users"

type UserFormProps = {
  user?: User
  submitLabel: string
  isSubmitting: boolean
  onCancel: () => void
  onSubmit: (values: UserCreateInput) => Promise<void>
}

type UserFormValues = Omit<UserCreateInput, "role"> & {
  role: UserRole | ""
}

export function UserForm({
  user,
  submitLabel,
  isSubmitting,
  onCancel,
  onSubmit,
}: UserFormProps) {
  const [values, setValues] = React.useState<UserFormValues>(() => ({
    name: user?.name ?? "",
    email: user?.email ?? "",
    password: "",
    role: user?.role ?? "",
  }))
  const isEdit = user !== undefined

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (values.role === "") {
      return
    }

    await onSubmit({
      ...values,
      role: values.role,
    })
  }

  return (
    <form className="space-y-4" onSubmit={handleSubmit}>
      <div className="grid gap-2">
        <Label htmlFor="user-name">Name</Label>
        <Input
          id="user-name"
          placeholder="Ada Lovelace"
          value={values.name}
          onChange={(event) =>
            setValues((current) => ({ ...current, name: event.target.value }))
          }
          required
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="user-email">Email</Label>
        <Input
          id="user-email"
          type="email"
          placeholder="ada@example.com"
          value={values.email}
          onChange={(event) =>
            setValues((current) => ({ ...current, email: event.target.value }))
          }
          required
        />
      </div>

      <div className="grid gap-2">
        <Label htmlFor="user-password">
          {isEdit ? "New Password" : "Password"}
        </Label>
        <Input
          id="user-password"
          type="password"
          placeholder={isEdit ? "Leave blank to keep current password" : "Password"}
          value={values.password}
          onChange={(event) =>
            setValues((current) => ({ ...current, password: event.target.value }))
          }
          required={!isEdit}
          minLength={isEdit && values.password === "" ? undefined : 8}
        />
      </div>

      <div className="grid gap-2">
        <Label>Role</Label>
        <Select
          value={values.role === "" ? undefined : String(values.role)}
          onValueChange={(value) =>
            setValues((current) => ({
              ...current,
              role: Number(value) as UserRole,
            }))
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select role" />
          </SelectTrigger>
          <SelectContent>
            {userRoles.map((role) => (
              <SelectItem key={role.value} value={String(role.value)}>
                {role.label}
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
