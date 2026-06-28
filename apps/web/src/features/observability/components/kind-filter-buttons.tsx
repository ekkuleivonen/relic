import { Button } from "@/components/ui/button"

export type KindFilterOption<T extends string> = {
  id: T
  label: string
}

type KindFilterButtonsProps<T extends string> = {
  options: KindFilterOption<T>[]
  value: T
  onChange: (value: T) => void
}

export function KindFilterButtons<T extends string>({
  options,
  value,
  onChange,
}: KindFilterButtonsProps<T>) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => (
        <Button
          key={option.id}
          type="button"
          size="sm"
          variant={value === option.id ? "default" : "outline"}
          onClick={() => onChange(option.id)}
        >
          {option.label}
        </Button>
      ))}
    </div>
  )
}
