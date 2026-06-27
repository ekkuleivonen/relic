import { Link } from "react-router"

import {
  isJobRunProvenanceRef,
  isUserProvenanceRef,
  provenanceHref,
  provenanceLabel,
} from "@/features/objects/lib/provenance-ref"
import type { User } from "@/types/auth"
import type { JobRunType } from "@/types/job-runs"

type ProvenanceReferenceLinkProps = {
  reference: string
  users: User[] | undefined
  jobRunTypes: Record<string, JobRunType>
  canLinkToUser: boolean
}

export function ProvenanceReferenceLink({
  reference,
  users,
  jobRunTypes,
  canLinkToUser,
}: ProvenanceReferenceLinkProps) {
  const href = provenanceHref(reference)
  const label = provenanceLabel(reference, { users, jobRunTypes })

  if (href && isJobRunProvenanceRef(reference)) {
    return (
      <Link className="text-sm underline-offset-4 hover:underline" to={href}>
        {label}
      </Link>
    )
  }

  if (href && isUserProvenanceRef(reference) && canLinkToUser) {
    return (
      <Link className="text-sm underline-offset-4 hover:underline" to={href}>
        {label}
      </Link>
    )
  }

  return <span className="text-sm">{label}</span>
}
