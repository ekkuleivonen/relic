import { Checkbox } from "@/components/ui/checkbox"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import type { SettingFieldDefinition } from "@/features/settings/lib/setting-keys"

type DurationSettingFieldProps = {
  definition: SettingFieldDefinition
  disabled?: boolean
  value: string
  onChange: (value: string) => void
}

export function DurationSettingField({
  definition,
  disabled = false,
  value,
  onChange,
}: DurationSettingFieldProps) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={definition.key}>{definition.label}</Label>
      <Input
        id={definition.key}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={definition.defaultValue}
        disabled={disabled}
        className="font-mono"
      />
      <p className="text-xs/6 text-muted-foreground">{definition.description}</p>
    </div>
  )
}

type BooleanSettingFieldProps = {
  definition: SettingFieldDefinition
  checked: boolean
  onCheckedChange: (checked: boolean) => void
}

export function BooleanSettingField({
  definition,
  checked,
  onCheckedChange,
}: BooleanSettingFieldProps) {
  return (
    <label className="flex items-start gap-3 rounded-lg border bg-background/60 p-3">
      <Checkbox
        checked={checked}
        onCheckedChange={(value) => onCheckedChange(value === true)}
      />
      <span>
        <span className="block text-sm font-medium">{definition.label}</span>
        <span className="mt-1 block text-xs/6 text-muted-foreground">
          {definition.description}
        </span>
      </span>
    </label>
  )
}
