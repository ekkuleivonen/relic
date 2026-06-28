import { matchPath, useLocation, useParams } from "react-router"

import { useBucket } from "@/features/buckets/hooks/use-buckets"
import { useObject } from "@/features/objects/hooks/use-objects"
import type { AppBreadcrumbItem } from "@/types/navigation"

export function useAppBreadcrumbs(): AppBreadcrumbItem[] {
  const { pathname } = useLocation()
  const { bucketId, objectId, jobRunId } = useParams()

  const isBucketDetail = Boolean(matchPath("/buckets/:bucketId", pathname))
  const isObjectDetail = Boolean(matchPath("/objects/:objectId", pathname))
  const isJobRunDetail = Boolean(matchPath("/job-runs/:jobRunId", pathname))

  const bucketQuery = useBucket(isBucketDetail ? bucketId : undefined)
  const objectQuery = useObject(isObjectDetail ? objectId : undefined)

  const crumbs: AppBreadcrumbItem[] = [{ label: "Home", href: "/" }]

  if (pathname === "/") {
    return [{ label: "Home" }]
  }

  if (pathname.startsWith("/buckets")) {
    crumbs.push({ label: "Buckets", href: "/buckets" })

    if (isBucketDetail) {
      crumbs.push({
        label: bucketQuery.data?.name ?? bucketId ?? "Bucket",
        isLoading: bucketQuery.isLoading,
      })
    }

    return crumbs
  }

  if (pathname.startsWith("/objects")) {
    crumbs.push({ label: "Objects", href: "/objects" })

    if (isObjectDetail) {
      crumbs.push({
        label: objectQuery.data?.key ?? objectId ?? "Object",
        isLoading: objectQuery.isLoading,
      })
    }

    return crumbs
  }

  if (pathname.startsWith("/job-runs")) {
    crumbs.push({ label: "Job runs", href: "/job-runs" })

    if (isJobRunDetail) {
      crumbs.push({
        label: jobRunId ?? "Job run",
      })
    }

    return crumbs
  }

  if (pathname.startsWith("/settings/upstream-capture")) {
    crumbs.push({ label: "Settings" })
    crumbs.push({ label: "Upstream capture" })
    return crumbs
  }

  if (pathname.startsWith("/settings/worker")) {
    crumbs.push({ label: "Settings" })
    crumbs.push({ label: "Worker" })
    return crumbs
  }

  if (pathname.startsWith("/settings/jobs")) {
    crumbs.push({ label: "Settings" })
    crumbs.push({ label: "Jobs" })
    return crumbs
  }

  if (pathname.startsWith("/users")) {
    crumbs.push({ label: "Users" })
    return crumbs
  }

  return crumbs
}
