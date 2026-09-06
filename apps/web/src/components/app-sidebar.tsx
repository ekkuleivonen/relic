import {
  ArchiveIcon,
  ArrowDownToLineIcon,
  ArrowUpFromLineIcon,
  BoxIcon,
  CogIcon,
  LayersIcon,
  ListTodoIcon,
  LogOutIcon,
  MoonIcon,
  RefreshCwIcon,
  Settings2Icon,
  SunIcon,
  UsersIcon,
  type LucideIcon,
} from "lucide-react"
import { Link, useLocation, useNavigate } from "react-router"

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
import { useLogout, useSession } from "@/hooks/use-session"

type SidebarNavItem = {
  title: string
  icon: LucideIcon
  url?: string
  match?: (pathname: string) => boolean
  adminOnly?: boolean
  comingSoon?: boolean
}

const sidebarGroups: Array<{ label: string; items: SidebarNavItem[] }> = [
  {
    label: "Data",
    items: [
      {
        title: "Objects",
        url: "/objects",
        icon: BoxIcon,
        match: (pathname) => pathname.startsWith("/objects"),
      },
      {
        title: "Collections",
        url: "/collections",
        icon: LayersIcon,
        match: (pathname) => pathname.startsWith("/collections"),
      },
    ],
  },
  {
    label: "Settings",
    items: [
      {
        title: "Buckets",
        url: "/buckets",
        icon: ArchiveIcon,
        match: (pathname) => pathname.startsWith("/buckets"),
      },
      {
        title: "Users",
        url: "/users",
        icon: UsersIcon,
        match: (pathname) => pathname.startsWith("/users"),
        adminOnly: true,
      },
      {
        title: "Upstream capture",
        url: "/settings/upstream-capture",
        icon: Settings2Icon,
        match: (pathname) => pathname.startsWith("/settings/upstream-capture"),
      },
      {
        title: "Worker",
        url: "/settings/worker",
        icon: CogIcon,
        match: (pathname) => pathname.startsWith("/settings/worker"),
        adminOnly: true,
      },
      {
        title: "Jobs",
        url: "/settings/jobs",
        icon: ListTodoIcon,
        match: (pathname) => pathname.startsWith("/settings/jobs"),
        adminOnly: true,
      },
    ],
  },
  {
    label: "Observability",
    items: [
      {
        title: "Bucket sync",
        url: "/bucket-sync",
        icon: RefreshCwIcon,
        match: (pathname) => pathname.startsWith("/bucket-sync"),
      },
      {
        title: "Object sync",
        url: "/object-sync",
        icon: BoxIcon,
        match: (pathname) => pathname.startsWith("/object-sync"),
      },
      {
        title: "Bucket events",
        url: "/bucket-events",
        icon: ArrowDownToLineIcon,
        match: (pathname) => pathname.startsWith("/bucket-events"),
      },
      {
        title: "Collection events",
        icon: ArrowUpFromLineIcon,
        comingSoon: true,
      },
    ],
  },
]

export function AppSidebar() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { resolvedTheme, setTheme } = useTheme()
  const sessionQuery = useSession()
  const logout = useLogout()
  const nextTheme = resolvedTheme === "dark" ? "light" : "dark"
  const isAdmin = sessionQuery.data?.user.role === "admin"

  async function handleLogout() {
    await logout.mutateAsync()
    navigate("/login", { replace: true })
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link to="/">
                <img src="/logo.svg" alt="" className="size-8 rounded-lg" />
                <div className="grid flex-1 text-left leading-tight">
                  <span className="truncate font-semibold">Pithosys</span>
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
        {sidebarGroups.map((group) => {
          const items = group.items.filter((item) => !item.adminOnly || isAdmin)
          if (items.length === 0) {
            return null
          }

          return (
            <SidebarGroup key={group.label}>
              <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {items.map((item) => (
                    <SidebarNavMenuItem
                      key={item.title}
                      item={item}
                      pathname={pathname}
                    />
                  ))}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          )
        })}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={() => void handleLogout()}
              tooltip="Sign out"
              disabled={logout.isPending}
            >
              <LogOutIcon />
              <span>{logout.isPending ? "Signing out..." : "Sign out"}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
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

type SidebarNavMenuItemProps = {
  item: SidebarNavItem
  pathname: string
}

function SidebarNavMenuItem({ item, pathname }: SidebarNavMenuItemProps) {
  if (item.comingSoon) {
    return (
      <SidebarMenuItem>
        <SidebarMenuButton disabled tooltip="Coming soon">
          <item.icon />
          <span>{item.title}</span>
          <span className="ml-auto text-[10px] text-muted-foreground group-data-[collapsible=icon]:hidden">
            Soon
          </span>
        </SidebarMenuButton>
      </SidebarMenuItem>
    )
  }

  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        asChild
        isActive={item.match?.(pathname) ?? false}
        tooltip={item.title}
      >
        <Link to={item.url ?? "/"}>
          <item.icon />
          <span>{item.title}</span>
        </Link>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}
