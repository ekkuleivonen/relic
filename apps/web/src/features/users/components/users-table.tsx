import { Badge } from "@/components/ui/badge"
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
import type { User } from "@/types/auth"

type UsersTableProps = {
  users: User[]
  isLoading: boolean
  onEdit: (user: User) => void
  onToggleDisabled: (user: User) => void
}

export function UsersTable({
  users,
  isLoading,
  onEdit,
  onToggleDisabled,
}: UsersTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    )
  }

  if (users.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No users yet. Create the first account to get started.
      </p>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Email</TableHead>
          <TableHead>Name</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Status</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {users.map((user) => (
          <TableRow key={user.id}>
            <TableCell>{user.email}</TableCell>
            <TableCell>{user.display_name || "—"}</TableCell>
            <TableCell>
              <Badge variant={user.role === "admin" ? "default" : "secondary"}>
                {user.role}
              </Badge>
            </TableCell>
            <TableCell>
              {user.disabled_at ? (
                <Badge variant="destructive">Disabled</Badge>
              ) : (
                <Badge variant="outline">Active</Badge>
              )}
            </TableCell>
            <TableCell className="text-right">
              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" size="sm" onClick={() => onEdit(user)}>
                  Edit
                </Button>
                <Button
                  type="button"
                  variant={user.disabled_at ? "outline" : "destructive"}
                  size="sm"
                  onClick={() => onToggleDisabled(user)}
                >
                  {user.disabled_at ? "Enable" : "Disable"}
                </Button>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
