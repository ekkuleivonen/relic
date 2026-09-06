package bucketevents

import (
	"context"
	"errors"
	"net/http"

	"github.com/danielgtaylor/huma/v2"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
	observabilityhttp "github.com/elei-io/pithosys/apps/api/internal/httpserver/observability"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/upstreamevents"
)

func Register(api huma.API, dependencies deps.Dependencies, basePath string) {
	huma.Register(api, huma.Operation{
		OperationID: "list-bucket-events",
		Method:      http.MethodGet,
		Path:        basePath + "/bucket-events",
		Summary:     "List bucket events",
		Tags:        []string{"Observability"},
	}, func(ctx context.Context, input *listBucketEventsInput) (*listBucketEventsOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("storage is not configured")
		}

		params, err := listBucketEventsParamsFromInput(input)
		if err != nil {
			return nil, huma.Error422UnprocessableEntity(err.Error())
		}

		events, err := dependencies.Storage.UpstreamEvents().ListUpstreamEvents(ctx, params)
		if err != nil {
			return nil, err
		}

		total, err := dependencies.Storage.UpstreamEvents().CountUpstreamEvents(ctx, params)
		if err != nil {
			return nil, err
		}

		limit := params.Limit
		if limit <= 0 {
			limit = 100
		}

		body := listBucketEventsBody{
			BucketEvents: make([]BucketEventResponse, 0, len(events)),
			Total:        total,
			Limit:        limit,
			Offset:       params.Offset,
		}
		for _, event := range events {
			body.BucketEvents = append(body.BucketEvents, BucketEventResponseFromStorage(event))
		}

		return &listBucketEventsOutput{Body: body}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "get-bucket-event-stats",
		Method:      http.MethodGet,
		Path:        basePath + "/bucket-events/stats",
		Summary:     "Get bucket event activity stats",
		Tags:        []string{"Observability"},
	}, func(ctx context.Context, input *bucketEventStatsInput) (*bucketEventStatsOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("storage is not configured")
		}

		params, err := listBucketEventsParamsFromStatsInput(input)
		if err != nil {
			return nil, huma.Error422UnprocessableEntity(err.Error())
		}
		if params.ReceivedAfter == nil || params.ReceivedBefore == nil {
			return nil, huma.Error422UnprocessableEntity("received_after and received_before are required")
		}

		stats, err := dependencies.Storage.UpstreamEvents().UpstreamEventActivityStats(ctx, storage.UpstreamEventActivityStatsParams{
			ListUpstreamEventsParams: params,
			Series:                   upstreamevents.BucketEventStatsSeries(),
		})
		if err != nil {
			return nil, huma.Error422UnprocessableEntity(err.Error())
		}

		return &bucketEventStatsOutput{Body: observabilityhttp.ActivityStatsResponseFromStorage(stats)}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "get-bucket-event",
		Method:      http.MethodGet,
		Path:        basePath + "/bucket-events/{id}",
		Summary:     "Get bucket event",
		Tags:        []string{"Observability"},
	}, func(ctx context.Context, input *getBucketEventInput) (*bucketEventOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("storage is not configured")
		}

		event, err := dependencies.Storage.UpstreamEvents().GetUpstreamEvent(ctx, input.ID)
		if errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("bucket event not found")
		}
		if err != nil {
			return nil, err
		}

		return &bucketEventOutput{Body: BucketEventResponseFromStorage(event)}, nil
	})
}

type listBucketEventsInput struct {
	BucketID       string `query:"bucket_id" example:"bucket_0123456789abcdef0123456789abcdef"`
	State          string `query:"state" example:"pending"`
	Category       string `query:"category" example:"created"`
	ReceivedAfter  string `query:"received_after" example:"2026-06-27T00:00:00Z"`
	ReceivedBefore string `query:"received_before" example:"2026-06-28T00:00:00Z"`
	Limit          int    `query:"limit" example:"100"`
	Offset         int    `query:"offset" example:"0"`
}

type bucketEventStatsInput struct {
	BucketID       string `query:"bucket_id" example:"bucket_0123456789abcdef0123456789abcdef"`
	State          string `query:"state" example:"pending"`
	Category       string `query:"category" example:"created"`
	ReceivedAfter  string `query:"received_after" example:"2026-06-27T00:00:00Z"`
	ReceivedBefore string `query:"received_before" example:"2026-06-28T00:00:00Z"`
}

type getBucketEventInput struct {
	ID string `path:"id" example:"upevt_0123456789abcdef0123456789abcdef"`
}

type listBucketEventsOutput struct {
	Body listBucketEventsBody
}

type listBucketEventsBody struct {
	BucketEvents []BucketEventResponse `json:"bucket_events"`
	Total        int                   `json:"total"`
	Limit        int                   `json:"limit"`
	Offset       int                   `json:"offset"`
}

type bucketEventStatsOutput struct {
	Body observabilityhttp.ActivityStatsResponse
}

type bucketEventOutput struct {
	Body BucketEventResponse
}

func listBucketEventsParamsFromInput(input *listBucketEventsInput) (storage.ListUpstreamEventsParams, error) {
	receivedAfter, err := observabilityhttp.ParseOptionalTime(input.ReceivedAfter)
	if err != nil {
		return storage.ListUpstreamEventsParams{}, err
	}
	receivedBefore, err := observabilityhttp.ParseOptionalTime(input.ReceivedBefore)
	if err != nil {
		return storage.ListUpstreamEventsParams{}, err
	}

	return storage.ListUpstreamEventsParams{
		BucketID:       input.BucketID,
		State:          storage.UpstreamEventState(input.State),
		Category:       input.Category,
		ReceivedAfter:  receivedAfter,
		ReceivedBefore: receivedBefore,
		Limit:          input.Limit,
		Offset:         input.Offset,
	}, nil
}

func listBucketEventsParamsFromStatsInput(input *bucketEventStatsInput) (storage.ListUpstreamEventsParams, error) {
	receivedAfter, err := observabilityhttp.ParseOptionalTime(input.ReceivedAfter)
	if err != nil {
		return storage.ListUpstreamEventsParams{}, err
	}
	receivedBefore, err := observabilityhttp.ParseOptionalTime(input.ReceivedBefore)
	if err != nil {
		return storage.ListUpstreamEventsParams{}, err
	}

	return storage.ListUpstreamEventsParams{
		BucketID:       input.BucketID,
		State:          storage.UpstreamEventState(input.State),
		Category:       input.Category,
		ReceivedAfter:  receivedAfter,
		ReceivedBefore: receivedBefore,
	}, nil
}
