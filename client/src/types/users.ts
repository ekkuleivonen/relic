export const userRoles = [
  { value: 1, label: "User" },
  { value: 2, label: "Admin" },
] as const

export type UserRole = (typeof userRoles)[number]["value"]

export type User = {
  id: string
  name: string
  email: string
  role: UserRole
  created_at: string
  updated_at: string
}

export type UserCreateInput = {
  name: string
  email: string
  password: string
  role: UserRole
}

export type UserUpdateInput = Partial<UserCreateInput>
