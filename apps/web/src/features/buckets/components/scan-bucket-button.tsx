import { Loader2Icon, ScanSearchIcon } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useScanBucket } from "@/features/buckets/hooks/use-buckets"

type ScanBucketButtonProps = {
  bucketId: string
}

export function ScanBucketButton({ bucketId }: ScanBucketButtonProps) {
  const scanBucket = useScanBucket(bucketId)

  return (
    <Button
      type="button"
      variant="outline"
      onClick={() => scanBucket.mutate()}
      disabled={scanBucket.isPending}
    >
      {scanBucket.isPending ? (
        <Loader2Icon className="animate-spin" />
      ) : (
        <ScanSearchIcon />
      )}
      Scan bucket
    </Button>
  )
}
