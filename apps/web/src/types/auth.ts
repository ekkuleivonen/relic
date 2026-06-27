export type UserRole = "admin" | "user"

export type User = {
  id: string
  email: string
  display_name?: string
  role: UserRole
  created_at: string
  updated_at: string
  disabled_at?: string | null
}

export type Session = {
  user: User
}

export type LoginInput = {
  email: string
  password: string
}

export type AuthConfig = {
  oidc_enabled: boolean
}

export type UserCreateInput = {
  email: string
  display_name?: string
  role?: UserRole
  password?: string
}

export type UserUpdateInput = {
  display_name?: string
  role?: UserRole
  disabled?: boolean
  password?: string
}

export const userRoles: Array<{ value: UserRole; label: string }> = [
  { value: "admin", label: "Admin" },
  { value: "user", label: "User" },
]
