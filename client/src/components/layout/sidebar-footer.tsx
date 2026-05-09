import * as React from "react"
import { Folder, LogOut, Moon, Settings, Sun } from "lucide-react"
import { Link, useNavigate } from "react-router"

import { useTheme } from "@/components/theme-provider"
import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { useLogout, useSession } from "@/hooks/use-session"

type SidebarFooterProps = {
  adminAction?: "admin" | "files"
}

export function SidebarFooter({ adminAction = "admin" }: SidebarFooterProps) {
  const navigate = useNavigate()
  const sessionQuery = useSession()
  const logout = useLogout()
  const { setTheme } = useTheme()
  const isDark = useResolvedDarkMode()
  const user = sessionQuery.data?.user
  const isAdmin = user?.role === 2

  async function handleLogout() {
    await logout.mutateAsync()
    navigate("/login", { replace: true })
  }

  if (!user) {
    return null
  }

  return (
    <div className="border-t pt-3">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm text-muted-foreground">
            {user.name}
          </div>
        </div>
        <div className="flex shrink-0 gap-1">
          {isAdmin && adminAction === "admin" && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button type="button" variant="outline" size="icon-sm" asChild>
                  <Link to="/admin">
                    <Settings />
                    <span className="sr-only">Admin settings</span>
                  </Link>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Admin settings</TooltipContent>
            </Tooltip>
          )}
          {isAdmin && adminAction === "files" && (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button type="button" variant="outline" size="icon-sm" asChild>
                  <Link to="/">
                    <Folder />
                    <span className="sr-only">File tree</span>
                  </Link>
                </Button>
              </TooltipTrigger>
              <TooltipContent>File tree</TooltipContent>
            </Tooltip>
          )}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size="icon-sm"
                onClick={() => setTheme(isDark ? "light" : "dark")}
              >
                {isDark ? <Sun /> : <Moon />}
                <span className="sr-only">
                  Switch to {isDark ? "light" : "dark"} mode
                </span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>
              Switch to {isDark ? "light" : "dark"} mode
            </TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="outline"
                size="icon-sm"
                onClick={() => void handleLogout()}
                disabled={logout.isPending}
              >
                <LogOut />
                <span className="sr-only">Log out</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent>Log out</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </div>
  )
}

function useResolvedDarkMode() {
  const [isDark, setIsDark] = React.useState(
    () => document.documentElement.classList.contains("dark")
  )

  React.useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains("dark"))
    })
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    })
    return () => observer.disconnect()
  }, [])

  return isDark
}
