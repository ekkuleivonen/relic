import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import { bucketTiers, type BucketTier } from "@/types/buckets"

const tierClasses: Record<BucketTier, string> = {
  1: "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300",
  2: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  3: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
  4: "border-violet-500/30 bg-violet-500/10 text-violet-700 dark:text-violet-300",
}

export function BucketTierBadge({ tier }: { tier: BucketTier }) {
  const tierLabel =
    bucketTiers.find((bucketTier) => bucketTier.value === tier)?.label ??
    `Tier ${tier}`

  return (
    <Badge variant="outline" className={cn("border", tierClasses[tier])}>
      {tierLabel}
    </Badge>
  )
}
