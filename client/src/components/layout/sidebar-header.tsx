type SidebarHeaderProps = {
  section?: "admin"
}

export function SidebarHeader({ section }: SidebarHeaderProps) {
  return (
    <div className="mb-8">
      <div className="flex items-center gap-2">
        <img src="/logo.svg" alt="" className="size-7 rounded-sm" />
        <div className="flex min-w-0 items-center gap-2">
          <div className="text-lg font-semibold tracking-tight">Relic</div>
          {section === "admin" && (
            <span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[0.625rem] font-medium tracking-wide text-blue-700 uppercase dark:text-blue-300">
              admin
            </span>
          )}
        </div>
      </div>
      <div className="mt-1 pl-9 text-xs text-muted-foreground">
        Every blob in its place.
      </div>
    </div>
  )
}
