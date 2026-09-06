import { Loader2Icon, RefreshCwIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useActiveBucketSync } from "@/features/buckets/hooks/use-active-bucket-sync"
import { useSyncBucket } from "@/features/buckets/hooks/use-buckets"

type SyncBucketButtonProps = {
  bucketId: string
}

export function SyncBucketButton({ bucketId }: SyncBucketButtonProps) {
  const syncBucket = useSyncBucket(bucketId)
  const activeSync = useActiveBucketSync(bucketId)
  const isBusy = syncBucket.isPending || activeSync.isActive

  return (
    <Button
      type="button"
      onClick={() => syncBucket.mutate()}
      disabled={isBusy}
    >
      {isBusy ? (
        <Loader2Icon className="animate-spin" />
      ) : (
        <RefreshCwIcon />
      )}
      {activeSync.isActive ? "Syncing…" : "Sync bucket"}
    </Button>
  )
}
