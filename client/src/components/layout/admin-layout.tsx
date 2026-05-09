import { NavLink, Outlet } from "react-router"

import { SidebarFooter } from "@/components/layout/sidebar-footer"
import { SidebarHeader } from "@/components/layout/sidebar-header"
import { cn } from "@/lib/utils"

const adminNavItems = [
  { to: "/admin/buckets", label: "Buckets" },
  { to: "/admin/users", label: "Users" },
  { to: "/admin/access-keys", label: "Access Keys" },
  { to: "/admin/folders", label: "Folders" },
  { to: "/admin/files", label: "Files" },
  { to: "/admin/blobs", label: "Blobs" },
] as const

export function AdminLayout() {
  return (
    <div className="min-h-svh bg-background text-foreground">
      <aside className="fixed inset-y-0 left-0 hidden w-56 flex-col border-r bg-sidebar px-4 py-5 lg:flex">
        <SidebarHeader section="admin" />
        <nav className="flex flex-1 flex-col gap-1">
          {adminNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "border-l px-3 py-2 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-foreground",
                  isActive && "border-primary bg-sidebar-accent text-foreground"
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <SidebarFooter adminAction="files" />
      </aside>
      <div className="lg:pl-56">
        <header className="border-b px-4 py-3 lg:hidden">
          <div className="text-sm font-semibold">Relic Bucket Admin</div>
          <nav className="mt-3 flex gap-3 overflow-x-auto text-sm">
            {adminNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    "whitespace-nowrap text-muted-foreground hover:text-foreground",
                    isActive && "text-foreground"
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
