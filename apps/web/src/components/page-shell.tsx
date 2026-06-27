import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

type PageShellProps = {
  children: ReactNode
  className?: string
  maxWidth?: "5xl" | "6xl" | "7xl"
}

const maxWidthClasses = {
  "5xl": "max-w-5xl",
  "6xl": "max-w-6xl",
  "7xl": "max-w-7xl",
} as const

export function PageShell({
  children,
  className,
  maxWidth = "7xl",
}: PageShellProps) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-6 py-8 lg:px-8",
        maxWidthClasses[maxWidth],
        className
      )}
    >
      {children}
    </div>
  )
}
