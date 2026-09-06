package storage

import "time"

type jobRunListFilterArgs struct {
	types           []string
	state           string
	traceID         string
	requestedByType string
	requestedByID   string
	targetType      string
	targetID        string
	createdAfter    *time.Time
	createdBefore   *time.Time
}

func jobRunListFilterArgsFromParams(params ListJobRunsParams) jobRunListFilterArgs {
	return jobRunListFilterArgs{
		types:           listJobRunTypeFilter(params),
		state:           string(params.State),
		traceID:         params.TraceID,
		requestedByType: params.RequestedByType,
		requestedByID:   params.RequestedByID,
		targetType:      params.TargetType,
		targetID:        params.TargetID,
		createdAfter:    params.CreatedAfter,
		createdBefore:   params.CreatedBefore,
	}
}

const jobRunListWhereClause = `
	(cardinality($1::text[]) = 0 OR type = ANY($1::text[]))
	AND ($2 = '' OR state = $2)
	AND ($3 = '' OR requested_by_type = $3)
	AND ($4 = '' OR requested_by_id = $4)
	AND ($5 = '' OR target_type = $5)
	AND ($6 = '' OR target_id = $6)
	AND ($7::timestamptz IS NULL OR created_at >= $7)
	AND ($8::timestamptz IS NULL OR created_at < $8)
	AND ($9 = '' OR trace_id = $9)
`

func (a jobRunListFilterArgs) queryArgs() []any {
	return []any{
		a.types,
		a.state,
		a.requestedByType,
		a.requestedByID,
		a.targetType,
		a.targetID,
		a.createdAfter,
		a.createdBefore,
		a.traceID,
	}
}
