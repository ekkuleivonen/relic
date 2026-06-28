import { matchPath, useLocation, useParams } from "react-router"

import { useBucket } from "@/features/buckets/hooks/use-buckets"
import { useCollection } from "@/features/collections/hooks/use-collections"
import { useJobRun } from "@/features/job-runs/hooks/use-job-runs"
import { useObject } from "@/features/objects/hooks/use-objects"
import type { JobRunType } from "@/types/job-runs"
import type { AppBreadcrumbItem } from "@/types/navigation"

export function useAppBreadcrumbs(): AppBreadcrumbItem[] {
  const { pathname } = useLocation()
  const { bucketId, objectId, jobRunId, collectionId, eventId } = useParams()

  const isBucketDetail = Boolean(matchPath("/buckets/:bucketId", pathname))
  const isObjectDetail = Boolean(matchPath("/objects/:objectId", pathname))
  const isJobRunDetail = Boolean(matchPath("/job-runs/:jobRunId", pathname))
  const isCollectionDetail = Boolean(
    matchPath("/collections/:collectionId", pathname)
  )
  const isBucketEventDetail = Boolean(
    matchPath("/bucket-events/:eventId", pathname)
  )

  const bucketQuery = useBucket(isBucketDetail ? bucketId : undefined)
  const objectQuery = useObject(isObjectDetail ? objectId : undefined)
  const collectionQuery = useCollection(
    isCollectionDetail ? collectionId : undefined
  )
  const jobRunQuery = useJobRun(isJobRunDetail ? jobRunId : undefined)

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

  if (pathname.startsWith("/collections")) {
    crumbs.push({ label: "Collections", href: "/collections" })

    if (isCollectionDetail) {
      crumbs.push({
        label: collectionQuery.data?.name ?? collectionId ?? "Collection",
        isLoading: collectionQuery.isLoading,
      })
    }

    return crumbs
  }

  if (pathname.startsWith("/bucket-sync")) {
    crumbs.push({ label: "Bucket sync" })
    return crumbs
  }

  if (pathname.startsWith("/object-sync")) {
    crumbs.push({ label: "Object sync" })
    return crumbs
  }

  if (pathname.startsWith("/bucket-events")) {
    crumbs.push({ label: "Bucket events", href: "/bucket-events" })

    if (isBucketEventDetail) {
      crumbs.push({
        label: eventId ?? "Event",
      })
    }

    return crumbs
  }

  if (pathname.startsWith("/collection-events")) {
    crumbs.push({ label: "Collection events" })
    return crumbs
  }

  if (pathname.startsWith("/job-runs")) {
    const parent = jobRunListCrumb(jobRunQuery.data?.type)

    crumbs.push({ label: parent.label, href: parent.href })

    if (isJobRunDetail) {
      crumbs.push({
        label: jobRunId ?? "Job run",
        isLoading: jobRunQuery.isLoading,
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

function jobRunListCrumb(type: JobRunType | undefined) {
  if (type === "sync_bucket" || type === "scan_bucket") {
    return { label: "Bucket sync", href: "/bucket-sync" }
  }

  if (
    type === "import_objects" ||
    type === "remove_objects" ||
    type === "refresh_objects"
  ) {
    return { label: "Object sync", href: "/object-sync" }
  }

  return { label: "Job run", href: "/bucket-sync" }
}
