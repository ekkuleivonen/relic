import { PencilIcon, Trash2Icon } from "lucide-react"

import { PermissionBadges } from "@/components/folder-access/permission-badges"
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
import type { FolderAccess } from "@/types/folder-access"

type FolderAccessTableProps = {
  grants: FolderAccess[]
  isLoading: boolean
  onEdit: (grant: FolderAccess) => void
  onRevoke: (grant: FolderAccess) => void
}

export function FolderAccessTable({
  grants,
  isLoading,
  onEdit,
  onRevoke,
}: FolderAccessTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
  }

  if (grants.length === 0) {
    return (
      <div className="border px-4 py-10 text-center text-sm text-muted-foreground">
        No folder access grants yet.
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>User</TableHead>
          <TableHead>Scope</TableHead>
          <TableHead>Permissions</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {grants.map((grant) => (
          <TableRow key={grant.id}>
            <TableCell>
              <div className="font-medium">{grant.user.name}</div>
              <div className="text-xs text-muted-foreground">
                {grant.user.email}
              </div>
            </TableCell>
            <TableCell className="font-mono text-xs">
              {grant.folder_path}
            </TableCell>
            <TableCell>
              <PermissionBadges permissions={grant.permissions} />
            </TableCell>
            <TableCell>
              <div className="flex justify-end gap-1">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      size="icon-sm"
                      onClick={() => onEdit(grant)}
                    >
                      <PencilIcon />
                      <span className="sr-only">Edit grant</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Edit permissions</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      type="button"
                      variant="destructive"
                      size="icon-sm"
                      onClick={() => onRevoke(grant)}
                    >
                      <Trash2Icon />
                      <span className="sr-only">Revoke grant</span>
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>Revoke this grant</TooltipContent>
                </Tooltip>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
