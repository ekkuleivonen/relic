import { Fragment } from "react"
import { Link } from "react-router"

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Skeleton } from "@/components/ui/skeleton"
import { useAppBreadcrumbs } from "@/hooks/use-app-breadcrumbs"

export function AppBreadcrumbs() {
  const crumbs = useAppBreadcrumbs()

  return (
    <Breadcrumb className="min-w-0 flex-1">
      <BreadcrumbList>
        {crumbs.map((crumb, index) => {
          const isLast = index === crumbs.length - 1

          return (
            <Fragment key={`${crumb.label}-${index}`}>
              {index > 0 && <BreadcrumbSeparator />}
              <BreadcrumbItem className="min-w-0">
                {isLast || !crumb.href ? (
                  crumb.isLoading ? (
                    <Skeleton className="h-4 w-24" />
                  ) : (
                    <BreadcrumbPage className="max-w-[min(100%,20rem)] truncate">
                      {crumb.label}
                    </BreadcrumbPage>
                  )
                ) : (
                  <BreadcrumbLink asChild>
                    <Link to={crumb.href} className="truncate">
                      {crumb.label}
                    </Link>
                  </BreadcrumbLink>
                )}
              </BreadcrumbItem>
            </Fragment>
          )
        })}
      </BreadcrumbList>
    </Breadcrumb>
  )
}
