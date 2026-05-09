import { BanIcon } from "lucide-react"
import type { ComponentProps, ReactNode } from "react"

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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import type { AccessKey } from "@/types/access-keys"

type AccessKeysTableProps = {
  accessKeys: AccessKey[]
  isLoading: boolean
  revokingKeyId?: string
  onRevoke: (accessKey: AccessKey) => void
}

export function AccessKeysTable({
  accessKeys,
  isLoading,
  revokingKeyId,
  onRevoke,
}: AccessKeysTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    )
  }

  if (accessKeys.length === 0) {
    return (
      <div className="border px-4 py-10 text-center text-sm text-muted-foreground">
        No access keys created yet.
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Name</TableHead>
          <TableHead>User</TableHead>
          <TableHead>Key ID</TableHead>
          <TableHead>Status</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>Last Used</TableHead>
          <TableHead className="text-right">Actions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {accessKeys.map((accessKey) => (
          <TableRow key={accessKey.id}>
            <TableCell className="font-medium">{accessKey.name}</TableCell>
            <TableCell>
              <div className="flex min-w-0 flex-col">
                <span className="truncate font-medium">{accessKey.user.name}</span>
                <span className="truncate text-xs text-muted-foreground">
                  {accessKey.user.email}
                </span>
              </div>
            </TableCell>
            <TableCell className="font-mono text-xs">{accessKey.key_id}</TableCell>
            <TableCell>
              {accessKey.revoked_at ? (
                <Badge variant="destructive">Revoked</Badge>
              ) : (
                <Badge variant="outline">Active</Badge>
              )}
            </TableCell>
            <TableCell>{formatDate(accessKey.created_at)}</TableCell>
            <TableCell>{formatOptionalDate(accessKey.last_used_at)}</TableCell>
            <TableCell>
              <div className="flex justify-end gap-1">
                <ActionButton
                  label="Revoke access key"
                  tooltip={
                    accessKey.revoked_at
                      ? "This access key has already been revoked."
                      : "Revoke this access key."
                  }
                  variant="destructive"
                  disabled={
                    accessKey.revoked_at !== null || revokingKeyId === accessKey.key_id
                  }
                  onClick={() => onRevoke(accessKey)}
                >
                  <BanIcon />
                </ActionButton>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function formatOptionalDate(value: string | null) {
  return value ? formatDate(value) : "Never"
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
  disabled?: boolean
  onClick: () => void
}

function ActionButton({
  label,
  tooltip,
  children,
  variant = "outline",
  disabled = false,
  onClick,
}: ActionButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant={variant}
          size="icon-sm"
          disabled={disabled}
          onClick={onClick}
        >
          {children}
          <span className="sr-only">{label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>{tooltip}</TooltipContent>
    </Tooltip>
  )
}
