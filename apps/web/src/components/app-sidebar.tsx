import {
  ArchiveIcon,
  BoxIcon,
  ListTodoIcon,
  MoonIcon,
  SunIcon,
} from "lucide-react"
import { Link, useLocation } from "react-router"

import { useTheme } from "@/components/theme-provider"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar"

const navItems = [
  {
    title: "Buckets",
    url: "/buckets",
    icon: ArchiveIcon,
    match: (pathname: string) => pathname.startsWith("/buckets"),
  },
  {
    title: "Objects",
    url: "/objects",
    icon: BoxIcon,
    match: (pathname: string) => pathname.startsWith("/objects"),
  },
  {
    title: "Job runs",
    url: "/job-runs",
    icon: ListTodoIcon,
    match: (pathname: string) => pathname.startsWith("/job-runs"),
  },
] as const

export function AppSidebar() {
  const { pathname } = useLocation()
  const { resolvedTheme, setTheme } = useTheme()
  const nextTheme = resolvedTheme === "dark" ? "light" : "dark"

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link to="/">
                <img src="/logo.svg" alt="" className="size-8 rounded-lg" />
                <div className="grid flex-1 text-left leading-tight">
                  <span className="truncate font-semibold">Relic</span>
                  <span className="truncate text-xs text-sidebar-foreground/70">
                    Every byte in its place.
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Admin</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => (
                <SidebarMenuItem key={item.url}>
                  <SidebarMenuButton
                    asChild
                    isActive={item.match(pathname)}
                    tooltip={item.title}
                  >
                    <Link to={item.url}>
                      <item.icon />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={() => setTheme(nextTheme)}
              tooltip={`Switch to ${nextTheme} mode`}
            >
              {nextTheme === "dark" ? <MoonIcon /> : <SunIcon />}
              <span>{nextTheme === "dark" ? "Dark" : "Light"} mode</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  )
}
