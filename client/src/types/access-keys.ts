import type { User } from "@/types/users"

export type AccessKey = {
  id: string
  user: User
  name: string
  key_id: string
  last_used_at: string | null
  revoked_at: string | null
  created_at: string
  updated_at: string
}

export type AccessKeyCreateInput = {
  user_id: string
  name: string
}

export type CreatedAccessKey = AccessKey & {
  secret_access_key: string
}
