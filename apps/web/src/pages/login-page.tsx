import * as React from "react"
import { Navigate, useLocation, useNavigate } from "react-router"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuthConfig } from "@/hooks/use-auth-config"
import { useLogin, useSession } from "@/hooks/use-session"
import { API_BASE_URL } from "@/lib/api"

export function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const authConfigQuery = useAuthConfig()
  const sessionQuery = useSession()
  const login = useLogin()
  const [email, setEmail] = React.useState("")
  const [password, setPassword] = React.useState("")
  const from = getRedirectPath(location.state)

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    await login.mutateAsync({ email, password })
    navigate(from, { replace: true })
  }

  if (sessionQuery.isLoading) {
    return (
      <div className="flex min-h-svh items-center justify-center bg-background p-6">
        <Skeleton className="h-64 w-full max-w-sm" />
      </div>
    )
  }

  if (sessionQuery.data) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Sign In</CardTitle>
          <p className="text-xs text-muted-foreground">
            Use your Pithosys account to continue.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="space-y-4" onSubmit={handleSubmit}>
            <div className="grid gap-2">
              <Label htmlFor="login-email">Email</Label>
              <Input
                id="login-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="login-password">Password</Label>
              <Input
                id="login-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
            <Button type="submit" className="w-full" disabled={login.isPending}>
              {login.isPending ? "Signing in..." : "Sign in"}
            </Button>
          </form>

          {authConfigQuery.data?.oidc_enabled ? (
            <>
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-card px-2 text-muted-foreground">Or</span>
                </div>
              </div>
              <Button asChild variant="outline" className="w-full">
                <a href={`${API_BASE_URL}/auth/oidc/start`}>Sign in with SSO</a>
              </Button>
            </>
          ) : null}
        </CardContent>
      </Card>
    </div>
  )
}

function getRedirectPath(state: unknown) {
  if (
    typeof state === "object" &&
    state !== null &&
    "from" in state &&
    typeof state.from === "object" &&
    state.from !== null &&
    "pathname" in state.from &&
    typeof state.from.pathname === "string" &&
    state.from.pathname !== "/login"
  ) {
    return state.from.pathname
  }

  return "/"
}
