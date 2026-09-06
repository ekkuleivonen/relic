package buckets

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/jobs"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/middleware"
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

		if err := validateUpstreamConfigJetstream("", input.Body.UpstreamConfig); err != nil {
			return nil, huma.Error400BadRequest(err.Error())
		}

		relicConfig := storage.BucketRelicConfig{}
		if input.Body.RelicConfig != nil {
			relicConfig = *input.Body.RelicConfig
		}

		var bucket storage.Bucket
		if err := dependencies.Storage.WithTx(ctx, func(ctx context.Context, tx *storage.Tx) error {
			createdBucket, err := tx.Buckets().CreateBucket(ctx, storage.CreateBucketParams{
				Name:                 input.Body.Name,
				Upstream:             storage.BucketUpstream(input.Body.Upstream),
				EndpointURL:          input.Body.EndpointURL,
				Region:               input.Body.Region,
				BucketName:           input.Body.BucketName,
				Prefix:               input.Body.Prefix,
				UpstreamConfig:       input.Body.UpstreamConfig,
				EncryptedCredentials: envelope,
				RelicConfig:          relicConfig,
			})
			if err != nil {
				return err
			}

			if _, err := createSyncBucketJob(ctx, dependencies, tx.JobRuns(), createdBucket.ID); err != nil {
				return err
			}

			bucket = createdBucket
			return nil
		}); err != nil {
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

		if input.Body.UpstreamConfig != nil {
			if err := validateUpstreamConfigJetstream(input.ID, *input.Body.UpstreamConfig); err != nil {
				return nil, huma.Error400BadRequest(err.Error())
			}
		}

		params := storage.UpdateBucketParams{
			ID:             input.ID,
			Name:           input.Body.Name,
			EndpointURL:    input.Body.EndpointURL,
			Region:         input.Body.Region,
			Prefix:         input.Body.Prefix,
			UpstreamConfig: input.Body.UpstreamConfig,
			RelicConfig: input.Body.RelicConfig,
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

		targetParams := storage.HasActiveWorkForTargetParams{
			TargetType: "bucket",
			TargetID:   input.ID,
			StaleAfter: jobStaleTimeout(ctx, dependencies.Storage),
		}

		if _, err := dependencies.Storage.JobRuns().FailActiveScanJobsForTarget(ctx, targetParams); err != nil {
			return nil, err
		}

		run, err := enqueueSyncBucketJob(ctx, dependencies, dependencies.Storage.JobRuns(), input.ID)
		if err != nil {
			if errors.Is(err, errSyncAlreadyInProgress) {
				blocking, findErr := dependencies.Storage.JobRuns().FindActiveWorkForTarget(ctx, targetParams)
				if findErr == nil {
					return nil, huma.Error409Conflict(fmt.Sprintf(
						"catalog work is already in progress for this bucket (%s %s)",
						blocking.Type,
						blocking.ID,
					))
				}
				return nil, huma.Error409Conflict("catalog work is already in progress for this bucket")
			}
			return nil, err
		}

		return &syncBucketOutput{
			Status: http.StatusAccepted,
			Body:   jobs.JobRunResponseFromStorage(run),
		}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "scan-bucket",
		Method:      http.MethodPost,
		Path:        basePath + "/buckets/{id}/scan",
		Summary:     "Scan bucket",
		Tags:        []string{"Buckets"},
	}, func(ctx context.Context, input *scanBucketInput) (*scanBucketOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("bucket dependencies are not configured")
		}

		if _, err := dependencies.Storage.Buckets().GetBucket(ctx, input.ID); errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("bucket not found")
		} else if err != nil {
			return nil, err
		}

		targetParams := storage.HasActiveWorkForTargetParams{
			TargetType: "bucket",
			TargetID:   input.ID,
			StaleAfter: jobStaleTimeout(ctx, dependencies.Storage),
		}
		active, err := dependencies.Storage.JobRuns().HasActiveWorkForTarget(ctx, targetParams)
		if err != nil {
			return nil, err
		}
		if active {
			blocking, findErr := dependencies.Storage.JobRuns().FindActiveWorkForTarget(ctx, targetParams)
			if findErr == nil {
				return nil, huma.Error409Conflict(fmt.Sprintf(
					"catalog work is already in progress for this bucket (%s %s)",
					blocking.Type,
					blocking.ID,
				))
			}
			return nil, huma.Error409Conflict("catalog work is already in progress for this bucket")
		}

		prefix := ""
		if input.Body != nil {
			prefix = input.Body.Prefix
		}

		run, err := createScanBucketJob(ctx, dependencies, dependencies.Storage.JobRuns(), input.ID, prefix)
		if err != nil {
			return nil, err
		}

		return &scanBucketOutput{
			Status: http.StatusAccepted,
			Body:   jobs.JobRunResponseFromStorage(run),
		}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "delete-bucket",
		Method:      http.MethodDelete,
		Path:        basePath + "/buckets/{id}",
		Summary:     "Delete bucket",
		Tags:        []string{"Buckets"},
	}, func(ctx context.Context, input *deleteBucketInput) (*deleteBucketOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("bucket dependencies are not configured")
		}

		err := dependencies.Storage.Buckets().DeleteBucket(ctx, input.ID)
		if errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("bucket not found")
		}
		if err != nil {
			return nil, err
		}

		return &deleteBucketOutput{Status: http.StatusNoContent}, nil
	})
}

var errSyncAlreadyInProgress = errors.New("sync already in progress")

func enqueueSyncBucketJob(
	ctx context.Context,
	dependencies deps.Dependencies,
	jobRuns storage.JobRunRepository,
	bucketID string,
) (storage.JobRun, error) {
	targetParams := storage.HasActiveWorkForTargetParams{
		TargetType: "bucket",
		TargetID:   bucketID,
		StaleAfter: jobStaleTimeout(ctx, dependencies.Storage),
	}

	resumable, err := jobRuns.FindResumableSyncJobRun(ctx, storage.FindResumableSyncJobRunParams{
		TargetType:  "bucket",
		TargetID:    bucketID,
		ScopePrefix: "",
	})
	if err == nil {
		return jobRuns.ResumeJobRun(ctx, resumable.ID)
	}
	if !errors.Is(err, storage.ErrNotFound) {
		return storage.JobRun{}, err
	}

	blocking, findErr := jobRuns.FindActiveWorkForTarget(ctx, targetParams)
	if findErr != nil && !errors.Is(findErr, storage.ErrNotFound) {
		return storage.JobRun{}, findErr
	}
	if findErr == nil && blocking.ID != "" {
		return storage.JobRun{}, errSyncAlreadyInProgress
	}

	return createSyncBucketJob(ctx, dependencies, jobRuns, bucketID)
}

func createSyncBucketJob(ctx context.Context, dependencies deps.Dependencies, jobRuns storage.JobRunRepository, bucketID string) (storage.JobRun, error) {
	requestedBy := middleware.RequestedByFromContext(ctx, dependencies)
	return jobRuns.CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeSyncBucket,
		RequestedByType: requestedBy.Type,
		RequestedByID:   requestedBy.ID,
		TargetType:      "bucket",
		TargetID:        bucketID,
		MaxAttempts:     storage.DefaultSyncBucketMaxAttempts,
		Input: storage.JobRunPayload{
			"bucket_id": bucketID,
		},
	})
}

func createScanBucketJob(ctx context.Context, dependencies deps.Dependencies, jobRuns storage.JobRunRepository, bucketID string, prefix string) (storage.JobRun, error) {
	input := storage.JobRunPayload{
		"bucket_id": bucketID,
	}
	if prefix != "" {
		input["prefix"] = prefix
	}

	requestedBy := middleware.RequestedByFromContext(ctx, dependencies)
	return jobRuns.CreateJobRun(ctx, storage.CreateJobRunParams{
		Type:            storage.JobTypeScanBucket,
		RequestedByType: requestedBy.Type,
		RequestedByID:   requestedBy.ID,
		TargetType:      "bucket",
		TargetID:        bucketID,
		Input:           input,
	})
}

func validateUpstreamConfigJetstream(bucketID string, config storage.BucketUpstreamConfig) error {
	if config == nil {
		return nil
	}
	if _, ok := config["jetstream"]; !ok {
		return nil
	}

	_, _, err := storage.ParseBucketJetStreamConfig(bucketID, config)
	return err
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
	RelicConfig    *storage.BucketRelicConfig    `json:"relic_config,omitempty"`
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

type scanBucketInput struct {
	ID   string `path:"id" example:"bucket_0123456789abcdef0123456789abcdef"`
	Body *scanBucketBody
}

type scanBucketBody struct {
	Prefix string `json:"prefix,omitempty" example:"photos/"`
}

type deleteBucketInput struct {
	ID string `path:"id" example:"bucket_0123456789abcdef0123456789abcdef"`
}

type updateBucketBody struct {
	Name           *string                          `json:"name,omitempty" example:"production-data"`
	EndpointURL    *string                          `json:"endpoint_url,omitempty" example:"https://s3.amazonaws.com"`
	Region         *string                          `json:"region,omitempty" example:"us-east-1"`
	Prefix         *string                          `json:"prefix,omitempty" example:"raw/"`
	UpstreamConfig *storage.BucketUpstreamConfig    `json:"upstream_config,omitempty"`
	Credentials    *map[string]any                  `json:"credentials,omitempty"`
	RelicConfig    *storage.BucketRelicConfig    `json:"relic_config,omitempty"`
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

type scanBucketOutput struct {
	Status int
	Body   jobs.JobRunResponse
}

type deleteBucketOutput struct {
	Status int
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
	RelicConfig    storage.BucketRelicConfig    `json:"relic_config"`
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
		RelicConfig:    bucket.RelicConfig,
		CreatedAt:      bucket.CreatedAt,
		UpdatedAt:      bucket.UpdatedAt,
	}
}

func jobStaleTimeout(ctx context.Context, store *storage.Store) time.Duration {
	if store == nil {
		return storage.DefaultJobStaleTimeout
	}

	setting, err := store.Settings().Get(ctx, storage.SettingWorkerJobStaleTimeout)
	if err != nil {
		return storage.DefaultJobStaleTimeout
	}

	parsed, err := storage.ParseSettingDuration(storage.SettingWorkerJobStaleTimeout, setting.Value)
	if err != nil {
		return storage.DefaultJobStaleTimeout
	}

	return parsed
}
