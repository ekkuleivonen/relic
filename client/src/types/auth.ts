import type { User } from "@/types/users"

export type Session = {
  user: User
}

export type LoginInput = {
  email: string
  password: string
}
