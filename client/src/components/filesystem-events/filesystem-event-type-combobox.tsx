import { StringOptionCombobox } from "@/components/filters/string-option-combobox"
import { FILESYSTEM_EVENT_TYPES } from "@/types/filesystem-events"

type FilesystemEventTypeComboboxProps = {
  value: string | undefined
  onChange: (eventType: string | undefined) => void
  disabled?: boolean
  placeholder?: string
}

export function FilesystemEventTypeCombobox({
  value,
  onChange,
  disabled,
  placeholder = "Any type",
}: FilesystemEventTypeComboboxProps) {
  return (
    <StringOptionCombobox
      options={FILESYSTEM_EVENT_TYPES}
      value={value}
      onChange={onChange}
      disabled={disabled}
      placeholder={placeholder}
      clearLabel={placeholder}
      searchPlaceholder="Search event types..."
      mono
    />
  )
}
