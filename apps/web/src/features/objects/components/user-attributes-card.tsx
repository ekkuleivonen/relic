import { PlusIcon, Trash2Icon } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { UserAttributeValueField } from "@/features/objects/components/user-attribute-value-field"
import { usePatchObjectAttributes } from "@/features/objects/hooks/use-patch-object-attributes"
import {
  displayUserAttributeValue,
  formatUserAttributeValue,
  inferUserAttributeValueType,
  parseUserAttributeValue,
} from "@/features/objects/lib/user-attribute-value"
import { extractApiError } from "@/lib/api"
import {
  userAttributeValueTypes,
  type UserAttributeValueType,
} from "@/types/objects"

type UserAttributeEntry = {
  path: string
  suffix: string
  value: unknown
  type: UserAttributeValueType
}

type UserAttributesCardProps = {
  objectId: string
  userAttributes: Record<string, unknown> | undefined
  isAdmin: boolean
}

export function UserAttributesCard({
  objectId,
  userAttributes,
  isAdmin,
}: UserAttributesCardProps) {
  const patchAttributes = usePatchObjectAttributes(objectId)
  const entries = flattenUserAttributes(userAttributes)
  const [newPath, setNewPath] = useState("")
  const [newType, setNewType] = useState<UserAttributeValueType>("string")
  const [newValue, setNewValue] = useState("")

  async function handleAdd() {
    const suffix = newPath.trim()
    if (!suffix) {
      return
    }

    try {
      await patchAttributes.mutateAsync({
        set: {
          [`user.${suffix}`]: parseUserAttributeValue(newValue, newType),
        },
      })
      setNewPath("")
      setNewType("string")
      setNewValue("")
    } catch (error) {
      toast.error(error instanceof Error ? error.message : extractApiError(error))
    }
  }

  async function handleUpdate(entry: UserAttributeEntry, valueText: string) {
    try {
      await patchAttributes.mutateAsync({
        set: {
          [entry.path]: parseUserAttributeValue(valueText, entry.type),
        },
      })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : extractApiError(error))
    }
  }

  async function handleDelete(path: string) {
    if (!window.confirm(`Delete ${path}?`)) {
      return
    }

    await patchAttributes.mutateAsync({
      delete: [path],
    })
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>User attributes</CardTitle>
        <CardDescription>
          {isAdmin
            ? "Custom metadata attached to this object under the user namespace."
            : "Custom metadata attached to this object."}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {entries.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No user attributes have been attached yet.
          </p>
        ) : (
          <div className="grid gap-3">
            {entries.map((entry) => (
              <UserAttributeRow
                key={`${entry.path}:${formatUserAttributeValue(entry.value, entry.type)}`}
                entry={entry}
                isAdmin={isAdmin}
                isPending={patchAttributes.isPending}
                onDelete={() => void handleDelete(entry.path)}
                onSave={(valueText) => void handleUpdate(entry, valueText)}
              />
            ))}
          </div>
        )}

        {isAdmin && (
          <div className="grid gap-3 rounded-lg border bg-background/60 p-4">
            <div className="text-sm font-medium">Add attribute</div>
            <div className="grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)_minmax(0,1fr)_auto] lg:items-end">
              <div className="grid gap-2">
                <Label htmlFor={`user-attr-path-${objectId}`}>Path</Label>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm text-muted-foreground">
                    user.
                  </span>
                  <Input
                    id={`user-attr-path-${objectId}`}
                    placeholder="owner"
                    value={newPath}
                    onChange={(event) => setNewPath(event.target.value)}
                  />
                </div>
              </div>
              <div className="grid gap-2">
                <Label htmlFor={`user-attr-type-${objectId}`}>Type</Label>
                <Select
                  value={newType}
                  onValueChange={(value) => {
                    setNewType(value as UserAttributeValueType)
                    if (value === "boolean" && newValue !== "true" && newValue !== "false") {
                      setNewValue("true")
                    }
                  }}
                >
                  <SelectTrigger id={`user-attr-type-${objectId}`} className="w-full">
                    <SelectValue placeholder="Select type" />
                  </SelectTrigger>
                  <SelectContent>
                    {userAttributeValueTypes.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor={`user-attr-value-${objectId}`}>Value</Label>
                <UserAttributeValueField
                  id={`user-attr-value-${objectId}`}
                  type={newType}
                  value={newValue}
                  onChange={setNewValue}
                />
              </div>
              <Button
                type="button"
                disabled={patchAttributes.isPending || !newPath.trim()}
                onClick={() => void handleAdd()}
              >
                <PlusIcon className="size-4" />
                Add
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function UserAttributeRow({
  entry,
  isAdmin,
  isPending,
  onDelete,
  onSave,
}: {
  entry: UserAttributeEntry
  isAdmin: boolean
  isPending: boolean
  onDelete: () => void
  onSave: (valueText: string) => void
}) {
  const formattedValue = formatUserAttributeValue(entry.value, entry.type)
  const [valueText, setValueText] = useState(formattedValue)
  const dirty = valueText !== formattedValue

  return (
    <div className="grid gap-3 rounded-lg border bg-background/60 p-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_auto] lg:items-center">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-xs font-medium text-muted-foreground">Path</div>
          <Badge variant="outline">{entry.type}</Badge>
        </div>
        <div className="mt-1 font-mono text-sm">{entry.path}</div>
      </div>
      <div className="grid gap-2">
        <Label className="text-xs font-medium text-muted-foreground">Value</Label>
        {isAdmin ? (
          <UserAttributeValueField
            type={entry.type}
            value={valueText}
            onChange={setValueText}
          />
        ) : (
          <div className="break-words text-sm">
            {displayUserAttributeValue(entry.value, entry.type)}
          </div>
        )}
      </div>
      {isAdmin && (
        <div className="flex gap-2 lg:justify-end">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isPending || !dirty}
            onClick={() => onSave(valueText)}
          >
            Save
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isPending}
            onClick={onDelete}
          >
            <Trash2Icon className="size-4" />
            Delete
          </Button>
        </div>
      )}
    </div>
  )
}

function flattenUserAttributes(
  value: Record<string, unknown> | undefined,
  prefix = "user"
): UserAttributeEntry[] {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return []
  }

  const entries: UserAttributeEntry[] = []

  for (const [key, child] of Object.entries(value)) {
    const path = `${prefix}.${key}`
    if (isNestedAttributeObject(child)) {
      entries.push(...flattenUserAttributes(child, path))
      continue
    }

    entries.push({
      path,
      suffix: path.slice("user.".length),
      value: child,
      type: inferUserAttributeValueType(child),
    })
  }

  return entries.sort((left, right) => left.path.localeCompare(right.path))
}

function isNestedAttributeObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}
