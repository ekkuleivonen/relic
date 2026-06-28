export type ActivityStatsBucket = "hour" | "day"

export type ActivityStatsPoint = {
  start: string
  counts: Record<string, number>
}

export type ActivityStats = {
  bucket: ActivityStatsBucket
  from: string
  to: string
  series: string[]
  points: ActivityStatsPoint[]
}

export type JobRunStatsParams = {
  types?: string[]
  type?: string
  state?: string
  requestedByType?: string
  requestedById?: string
  targetType?: string
  targetId?: string
  createdAfter: string
  createdBefore: string
}

export type BucketEventStatsParams = {
  bucketId?: string
  state?: string
  receivedAfter: string
  receivedBefore: string
}
