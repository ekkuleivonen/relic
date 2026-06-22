import { Badge } from "@/components/ui/badge"
import type { UserRole } from "@/types/users"

const roleLabels: Record<UserRole, string> = {
  1: "User",
  2: "Admin",
}

export function UserRoleBadge({ role }: { role: UserRole }) {
  return (
    <Badge variant={role === 2 ? "default" : "outline"}>{roleLabels[role]}</Badge>
  )
}
