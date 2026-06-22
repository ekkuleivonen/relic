import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { Permission, PERMISSION_OPTIONS } from "@/types/folder-access"

type PermissionPickerProps = {
  value: number
  onChange: (next: number) => void
}

const READ_DEPENDENT_BITS = Permission.WRITE | Permission.DELETE | Permission.ENRICH

export function PermissionPicker({ value, onChange }: PermissionPickerProps) {
  function toggle(bit: number, checked: boolean) {
    let next = checked ? value | bit : value & ~bit

    if ((bit & READ_DEPENDENT_BITS) !== 0 && checked) {
      next |= Permission.READ
    }

    if (bit === Permission.READ && !checked) {
      // Stripping read also strips the bits that depend on it.
      next &= ~READ_DEPENDENT_BITS
    }

    onChange(next)
  }

  return (
    <div className="grid gap-2">
      <Label>Permissions</Label>
      <div className="grid gap-2 rounded-md border p-3">
        {PERMISSION_OPTIONS.map((option) => {
          const checked = (value & option.bit) !== 0
          return (
            <label
              key={option.bit}
              className="flex cursor-pointer items-start gap-3 text-sm"
            >
              <Checkbox
                className="mt-0.5"
                checked={checked}
                onCheckedChange={(next) => toggle(option.bit, next === true)}
              />
              <div className="grid gap-0.5">
                <div className="font-medium">
                  {option.label}
                  <span className="ml-2 font-mono text-xs text-muted-foreground">
                    {option.letter}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground">
                  {option.description}
                </div>
              </div>
            </label>
          )
        })}
      </div>
    </div>
  )
}
