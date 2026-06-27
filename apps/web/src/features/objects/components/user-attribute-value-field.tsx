import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import type { UserAttributeValueType } from "@/types/objects"

type UserAttributeValueFieldProps = {
  type: UserAttributeValueType
  value: string
  onChange: (value: string) => void
  id?: string
  disabled?: boolean
}

export function UserAttributeValueField({
  type,
  value,
  onChange,
  id,
  disabled = false,
}: UserAttributeValueFieldProps) {
  if (type === "boolean") {
    return (
      <Select value={value || "false"} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger id={id} className="w-full">
          <SelectValue placeholder="Select value" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="true">true</SelectItem>
          <SelectItem value="false">false</SelectItem>
        </SelectContent>
      </Select>
    )
  }

  if (type === "timestamp") {
    return (
      <Input
        id={id}
        type="datetime-local"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    )
  }

  return (
    <Input
      id={id}
      type={type === "integer" || type === "float" ? "number" : "text"}
      step={type === "integer" ? "1" : type === "float" ? "any" : undefined}
      inputMode={type === "integer" || type === "float" ? "decimal" : undefined}
      value={value}
      disabled={disabled}
      placeholder={valuePlaceholder(type)}
      onChange={(event) => onChange(event.target.value)}
    />
  )
}

function valuePlaceholder(type: UserAttributeValueType) {
  switch (type) {
    case "integer":
      return "42"
    case "float":
      return "3.14"
    case "string":
    default:
      return "finance"
  }
}
