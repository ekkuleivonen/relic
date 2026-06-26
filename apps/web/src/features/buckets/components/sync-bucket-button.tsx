import { Loader2Icon, RefreshCwIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useSyncBucket } from "@/features/buckets/hooks/use-buckets"

type SyncBucketButtonProps = {
  bucketId: string
}

export function SyncBucketButton({ bucketId }: SyncBucketButtonProps) {
  const syncBucket = useSyncBucket(bucketId)

  return (
    <Button
      type="button"
      onClick={() => syncBucket.mutate()}
      disabled={syncBucket.isPending}
    >
      {syncBucket.isPending ? (
        <Loader2Icon className="animate-spin" />
      ) : (
        <RefreshCwIcon />
      )}
      Sync bucket
    </Button>
  )
}
