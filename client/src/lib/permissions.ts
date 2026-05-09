export const PERM = {
  READ: 1,
  WRITE: 2,
  DELETE: 4,
  ENRICH: 8,
} as const

export type PermissionBit = (typeof PERM)[keyof typeof PERM]

export function can(effective: number, bit: PermissionBit): boolean {
  return (effective & bit) === bit
}
