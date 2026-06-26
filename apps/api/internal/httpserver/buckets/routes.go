package buckets

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/jobs"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func Register(api huma.API, dependencies deps.Dependencies, basePath string) {
	huma.Register(api, huma.Operation{
		OperationID: "create-bucket",
		Method:      http.MethodPost,
		Path:        basePath + "/buckets",
		Summary:     "Create bucket",
		Tags:        []string{"Buckets"},
	}, func(ctx context.Context, input *createBucketInput) (*bucketOutput, error) {
		if dependencies.Storage == nil || dependencies.Secrets == nil {
			return nil, huma.Error500InternalServerError("bucket dependencies are not configured")
		}

		credentials, err := json.Marshal(input.Body.Credentials)
		if err != nil {
			return nil, huma.Error400BadRequest("credentials must be valid JSON")
		}

		envelope, err := dependencies.Secrets.Encrypt(ctx, credentials)
		if err != nil {
			return nil, err
		}

		bucket, err := dependencies.Storage.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
			Name:                 input.Body.Name,
			Upstream:             storage.BucketUpstream(input.Body.Upstream),
			EndpointURL:          input.Body.EndpointURL,
			Region:               input.Body.Region,
			BucketName:           input.Body.BucketName,
			Prefix:               input.Body.Prefix,
			UpstreamConfig:       input.Body.UpstreamConfig,
			EncryptedCredentials: envelope,
			PluginSettings:       input.Body.PluginSettings,
		})
		if err != nil {
			return nil, err
		}

		return &bucketOutput{Body: bucketResponseFromStorage(bucket)}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "list-buckets",
		Method:      http.MethodGet,
		Path:        basePath + "/buckets",
		Summary:     "List buckets",
		Tags:        []string{"Buckets"},
	}, func(ctx context.Context, input *listBucketsInput) (*listBucketsOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("bucket dependencies are not configured")
		}

		buckets, err := dependencies.Storage.Buckets().ListBuckets(ctx, storage.ListBucketsParams{
			Upstream: storage.BucketUpstream(input.Upstream),
			Limit:    input.Limit,
			Offset:   input.Offset,
		})
		if err != nil {
			return nil, err
		}

		body := listBucketsBody{Buckets: make([]bucketResponse, 0, len(buckets))}
		for _, bucket := range buckets {
			body.Buckets = append(body.Buckets, bucketResponseFromStorage(bucket))
		}

		return &listBucketsOutput{Body: body}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "get-bucket",
		Method:      http.MethodGet,
		Path:        basePath + "/buckets/{id}",
		Summary:     "Get bucket",
		Tags:        []string{"Buckets"},
	}, func(ctx context.Context, input *getBucketInput) (*bucketOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("bucket dependencies are not configured")
		}

		bucket, err := dependencies.Storage.Buckets().GetBucket(ctx, input.ID)
		if errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("bucket not found")
		}
		if err != nil {
			return nil, err
		}

		return &bucketOutput{Body: bucketResponseFromStorage(bucket)}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "update-bucket",
		Method:      http.MethodPatch,
		Path:        basePath + "/buckets/{id}",
		Summary:     "Update bucket",
		Tags:        []string{"Buckets"},
	}, func(ctx context.Context, input *updateBucketInput) (*bucketOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("bucket dependencies are not configured")
		}

		params := storage.UpdateBucketParams{
			ID:             input.ID,
			Name:           input.Body.Name,
			EndpointURL:    input.Body.EndpointURL,
			Region:         input.Body.Region,
			Prefix:         input.Body.Prefix,
			UpstreamConfig: input.Body.UpstreamConfig,
			PluginSettings: input.Body.PluginSettings,
		}

		if input.Body.Credentials != nil {
			if dependencies.Secrets == nil {
				return nil, huma.Error500InternalServerError("bucket dependencies are not configured")
			}

			credentials, err := json.Marshal(input.Body.Credentials)
			if err != nil {
				return nil, huma.Error400BadRequest("credentials must be valid JSON")
			}

			envelope, err := dependencies.Secrets.Encrypt(ctx, credentials)
			if err != nil {
				return nil, err
			}
			params.EncryptedCredentials = &envelope
		}

		bucket, err := dependencies.Storage.Buckets().UpdateBucket(ctx, params)
		if errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("bucket not found")
		}
		if err != nil {
			return nil, err
		}

		return &bucketOutput{Body: bucketResponseFromStorage(bucket)}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "sync-bucket",
		Method:      http.MethodPost,
		Path:        basePath + "/buckets/{id}/sync",
		Summary:     "Sync bucket",
		Tags:        []string{"Buckets"},
	}, func(ctx context.Context, input *syncBucketInput) (*syncBucketOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("bucket dependencies are not configured")
		}

		if _, err := dependencies.Storage.Buckets().GetBucket(ctx, input.ID); errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("bucket not found")
		} else if err != nil {
			return nil, err
		}

		run, err := dependencies.Storage.JobRuns().CreateJobRun(ctx, storage.CreateJobRunParams{
			Type:            storage.JobTypeSyncBucket,
			RequestedByType: "api",
			TargetType:      "bucket",
			TargetID:        input.ID,
			Input: storage.JobRunPayload{
				"bucket_id": input.ID,
			},
		})
		if err != nil {
			return nil, err
		}

		return &syncBucketOutput{
			Status: http.StatusAccepted,
			Body:   jobs.JobRunResponseFromStorage(run),
		}, nil
	})
}

type createBucketInput struct {
	Body createBucketBody
}

type createBucketBody struct {
	Name           string                          `json:"name" example:"production-data"`
	Upstream       string                          `json:"upstream" example:"s3"`
	EndpointURL    string                          `json:"endpoint_url" example:"https://s3.amazonaws.com"`
	Region         string                          `json:"region" example:"us-east-1"`
	BucketName     string                          `json:"bucket_name" example:"example-bucket"`
	Prefix         string                          `json:"prefix" example:"raw/"`
	UpstreamConfig storage.BucketUpstreamConfig    `json:"upstream_config"`
	Credentials    map[string]any                  `json:"credentials"`
	PluginSettings storage.BucketPluginSettingsMap `json:"plugin_settings"`
}

type listBucketsInput struct {
	Upstream string `query:"upstream" example:"s3"`
	Limit    int    `query:"limit" example:"100"`
	Offset   int    `query:"offset" example:"0"`
}

type getBucketInput struct {
	ID string `path:"id" example:"bucket_0123456789abcdef0123456789abcdef"`
}

type updateBucketInput struct {
	ID   string `path:"id" example:"bucket_0123456789abcdef0123456789abcdef"`
	Body updateBucketBody
}

type syncBucketInput struct {
	ID string `path:"id" example:"bucket_0123456789abcdef0123456789abcdef"`
}

type updateBucketBody struct {
	Name           *string                          `json:"name,omitempty" example:"production-data"`
	EndpointURL    *string                          `json:"endpoint_url,omitempty" example:"https://s3.amazonaws.com"`
	Region         *string                          `json:"region,omitempty" example:"us-east-1"`
	Prefix         *string                          `json:"prefix,omitempty" example:"raw/"`
	UpstreamConfig *storage.BucketUpstreamConfig    `json:"upstream_config,omitempty"`
	Credentials    *map[string]any                  `json:"credentials,omitempty"`
	PluginSettings *storage.BucketPluginSettingsMap `json:"plugin_settings,omitempty"`
}

type bucketOutput struct {
	Body bucketResponse
}

type listBucketsOutput struct {
	Body listBucketsBody
}

type syncBucketOutput struct {
	Status int
	Body   jobs.JobRunResponse
}

type listBucketsBody struct {
	Buckets []bucketResponse `json:"buckets"`
}

type bucketResponse struct {
	ID             string                          `json:"id" example:"bucket_0123456789abcdef0123456789abcdef"`
	Name           string                          `json:"name" example:"production-data"`
	Upstream       storage.BucketUpstream          `json:"upstream" example:"s3"`
	EndpointURL    string                          `json:"endpoint_url" example:"https://s3.amazonaws.com"`
	Region         string                          `json:"region" example:"us-east-1"`
	BucketName     string                          `json:"bucket_name" example:"example-bucket"`
	Prefix         string                          `json:"prefix" example:"raw/"`
	UpstreamConfig storage.BucketUpstreamConfig    `json:"upstream_config"`
	PluginSettings storage.BucketPluginSettingsMap `json:"plugin_settings"`
	CreatedAt      time.Time                       `json:"created_at"`
	UpdatedAt      time.Time                       `json:"updated_at"`
}

func bucketResponseFromStorage(bucket storage.Bucket) bucketResponse {
	return bucketResponse{
		ID:             bucket.ID,
		Name:           bucket.Name,
		Upstream:       bucket.Upstream,
		EndpointURL:    bucket.EndpointURL,
		Region:         bucket.Region,
		BucketName:     bucket.BucketName,
		Prefix:         bucket.Prefix,
		UpstreamConfig: bucket.UpstreamConfig,
		PluginSettings: bucket.PluginSettings,
		CreatedAt:      bucket.CreatedAt,
		UpdatedAt:      bucket.UpdatedAt,
	}
}
