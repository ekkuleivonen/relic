package upstreamevents

import (
	"context"
	"net/http"
	"strings"

	"github.com/danielgtaylor/huma/v2"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/packages/storage"
	upstreameventsingest "github.com/ekkuleivonen/relic/packages/upstreamevents"
)

func Register(api huma.API, dependencies deps.Dependencies, basePath string) {
	huma.Register(api, huma.Operation{
		OperationID:   "receive-s3-upstream-events",
		Method:        http.MethodPost,
		Path:          basePath + "/upstream-events/s3",
		Summary:       "Receive S3-compatible upstream notifications",
		Description:   "Accepts bucket object notifications from S3-compatible providers and stores them in the upstream_events inbox for asynchronous processing.",
		Tags:          []string{"Upstream Events"},
		DefaultStatus: http.StatusAccepted,
	}, func(ctx context.Context, input *receiveS3EventsInput) (*receiveS3EventsOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("upstream event dependencies are not configured")
		}
		if err := authorizeWebhook(input.Authorization, dependencies.Config.UpstreamEventsWebhookSecret); err != nil {
			return nil, err
		}
		if len(input.RawBody) == 0 {
			return nil, huma.Error400BadRequest("request body is required")
		}

		result, err := upstreameventsingest.IngestS3Notification(
			ctx,
			dependencies.Storage.UpstreamEvents(),
			input.RawBody,
			storage.UpstreamEventTransportWebhook,
			nil,
		)
		if err != nil {
			return nil, huma.Error400BadRequest(err.Error())
		}

		return &receiveS3EventsOutput{
			Body: receiveS3EventsBody{
				Accepted:  result.Accepted,
				Duplicate: result.Duplicate,
				Ignored:   result.Ignored,
				EventIDs:  result.EventIDs,
			},
		}, nil
	})
}

type receiveS3EventsInput struct {
	Authorization string `header:"Authorization" doc:"Optional bearer token when UPSTREAM_EVENTS_WEBHOOK_SECRET is configured."`
	RawBody       []byte `contentType:"application/json" doc:"Raw upstream notification payload."`
}

type receiveS3EventsOutput struct {
	Body receiveS3EventsBody
}

type receiveS3EventsBody struct {
	Accepted  int      `json:"accepted" doc:"Number of notification records stored for processing."`
	Duplicate int      `json:"duplicate" doc:"Number of duplicate notification records ignored."`
	Ignored   int      `json:"ignored" doc:"Number of unsupported or empty notification records ignored."`
	EventIDs  []string `json:"event_ids" doc:"IDs of newly stored upstream events."`
}

func authorizeWebhook(authorization, secret string) error {
	if secret == "" {
		return nil
	}

	token := strings.TrimSpace(authorization)
	if strings.HasPrefix(strings.ToLower(token), "bearer ") {
		token = strings.TrimSpace(token[7:])
	}
	if token == "" || token != secret {
		return huma.Error401Unauthorized("invalid upstream events webhook credentials")
	}

	return nil
}
