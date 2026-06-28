package storage

import "time"

type upstreamEventListFilterArgs struct {
	bucketID       string
	state          string
	category       string
	receivedAfter  *time.Time
	receivedBefore *time.Time
}

func upstreamEventListFilterArgsFromParams(params ListUpstreamEventsParams) upstreamEventListFilterArgs {
	return upstreamEventListFilterArgs{
		bucketID:       params.BucketID,
		state:          string(params.State),
		category:       params.Category,
		receivedAfter:  params.ReceivedAfter,
		receivedBefore: params.ReceivedBefore,
	}
}

const upstreamEventListWhereClause = `
	($1 = '' OR bucket_id = $1)
	AND ($2 = '' OR state = $2)
	AND ($3::timestamptz IS NULL OR received_at >= $3)
	AND ($4::timestamptz IS NULL OR received_at < $4)
	AND ($5 = '' OR (` + upstreamEventCategoryCase + `) = $5)
`

func (a upstreamEventListFilterArgs) queryArgs() []any {
	return []any{
		a.bucketID,
		a.state,
		a.receivedAfter,
		a.receivedBefore,
		a.category,
	}
}

const upstreamEventCategoryCase = `
	CASE
		WHEN event_name LIKE 'ObjectCreated:%' OR event_name LIKE 's3:ObjectCreated:%' THEN 'created'
		WHEN event_name LIKE 'ObjectRemoved:%' OR event_name LIKE 's3:ObjectRemoved:%' THEN 'removed'
		WHEN event_name LIKE '%Tagging%' OR event_name LIKE 'ObjectAcl:%' THEN 'metadata_changed'
		ELSE 'other'
	END
`
