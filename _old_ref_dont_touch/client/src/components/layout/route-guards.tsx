import { Navigate, Outlet, useLocation } from "react-router"

import { SearchPaletteProvider } from "@/components/search/search-palette-provider"
import { Skeleton } from "@/components/ui/skeleton"
import { useSession } from "@/hooks/use-session"

type RequireSessionProps = {
  requireAdmin?: boolean
}

export function RequireSession({ requireAdmin = false }: RequireSessionProps) {
  const location = useLocation()
  const sessionQuery = useSession()

  if (sessionQuery.isLoading) {
    return <SessionLoading />
  }

  if (!sessionQuery.data) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (requireAdmin && sessionQuery.data.user.role !== 2) {
    return <Navigate to="/" replace />
  }

  // Mount the search palette host inside the auth boundary so Cmd+K and the
  // sidebar trigger are available everywhere a logged-in user is, without
  // duplicating the provider in every layout.
  return (
    <SearchPaletteProvider>
      <Outlet />
    </SearchPaletteProvider>
  )
}

function SessionLoading() {
  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm space-y-3">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  )
}
