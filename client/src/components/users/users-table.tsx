import { PencilIcon, Trash2Icon } from "lucide-react"
import type { ComponentProps, ReactNode } from "react"

import { UserRoleBadge } from "@/components/users/user-role-badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { User } from "@/types/users"

type UsersTableProps = {
  users: User[]
  isLoading: boolean
  onEdit: (user: User) => void
  onDelete: (user: User) => void
}

export function UsersTable({
  users,
  isLoading,
  onEdit,
  onDelete,
}: UsersTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
  }

  if (users.length === 0) {
    return (
      <div className="border px-4 py-10 text-center text-sm text-muted-foreground">
        No users created yet.
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>Email</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>Updated</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {users.map((user) => (
          <TableRow key={user.id}>
            <TableCell className="font-medium">{user.name}</TableCell>
            <TableCell>{user.email}</TableCell>
            <TableCell>
              <UserRoleBadge role={user.role} />
            </TableCell>
            <TableCell>{formatDate(user.created_at)}</TableCell>
            <TableCell>{formatDate(user.updated_at)}</TableCell>
            <TableCell>
              <div className="flex justify-end gap-1">
                <ActionButton
                  label="Edit user"
                  tooltip="Edit user profile, role, or reset password."
                  onClick={() => onEdit(user)}
                >
                  <PencilIcon />
                </ActionButton>
                <ActionButton
                  label="Delete user"
                  tooltip="Delete this user and revoke related access."
                  variant="destructive"
                  onClick={() => onDelete(user)}
                >
                  <Trash2Icon />
                </ActionButton>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

type ActionButtonProps = {
  label: string
  tooltip: string
  children: ReactNode
  variant?: ComponentProps<typeof Button>["variant"]
  onClick: () => void
}

function ActionButton({
  label,
  tooltip,
  children,
  variant = "outline",
  onClick,
}: ActionButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button type="button" variant={variant} size="icon-sm" onClick={onClick}>
          {children}
          <span className="sr-only">{label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  )
}
