package jobs

import (
	"context"

	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

const (
	DefaultHeadConcurrency = 8
	DefaultUpsertBatchSize = 100
)

type ExecuteObjectMutationOptions struct {
	Store           *storage.Store
	Run             storage.JobRun
	Bucket          storage.Bucket
	Client          s3compat.ObjectClient
	Objects         []ObjectEvidence
	ProgressAction  string
	ResultCountKey  string
	HeadConcurrency int
	UpsertBatchSize int
}

func ExecuteObjectMutation(ctx context.Context, options ExecuteObjectMutationOptions) (storage.JobRunPayload, error) {
	headConcurrency := options.HeadConcurrency
	if headConcurrency <= 0 {
		headConcurrency = DefaultHeadConcurrency
	}
	upsertBatchSize := options.UpsertBatchSize
	if upsertBatchSize <= 0 {
		upsertBatchSize = DefaultUpsertBatchSize
	}

	total := len(options.Objects)
	if err := updateObjectMutationProgress(ctx, options.Store, options.Run.ID, options.ProgressAction, "heading", total, 0, 0); err != nil {
		return nil, err
	}

	headResults, err := HeadObjects(ctx, options.Objects, headConcurrency, HeadObjectFuncForClient(options.Client, options.Bucket.BucketName))
	if err != nil {
		return nil, err
	}
	if err := updateObjectMutationProgress(ctx, options.Store, options.Run.ID, options.ProgressAction, "headed", total, len(headResults), 0); err != nil {
		return nil, err
	}

	upserted := 0
	upsertParams := UpsertObjectParamsFromHeadResults(options.Bucket.ID, options.Run.ID, headResults)
	for _, batch := range UpsertObjectParamBatches(upsertParams, upsertBatchSize) {
		objects, err := options.Store.Objects().UpsertObjects(ctx, batch)
		if err != nil {
			return nil, err
		}
		upserted += len(objects)
		if err := updateObjectMutationProgress(ctx, options.Store, options.Run.ID, options.ProgressAction, "upserting", total, len(headResults), upserted); err != nil {
			return nil, err
		}
	}

	return storage.JobRunPayload{
		"bucket_id":            options.Bucket.ID,
		"objects_total":        total,
		"objects_headed":       len(headResults),
		"objects_upserted":     upserted,
		"head_concurrency":     headConcurrency,
		"upsert_batch_size":    upsertBatchSize,
		options.ResultCountKey: upserted,
	}, nil
}

func UpsertObjectParamsFromHeadResults(bucketID string, runID string, results []HeadObjectResult) []storage.UpsertObjectParams {
	params := make([]storage.UpsertObjectParams, 0, len(results))
	for _, result := range results {
		params = append(params, storage.UpsertObjectParams{
			BucketID:   bucketID,
			Key:        result.Evidence.Key,
			VersionID:  result.Evidence.VersionID,
			Attributes: result.Attributes,
			AttributeProvenance: storage.ObjectAttributeProvenance{
				"upstream": runID,
			},
		})
	}

	return params
}

func UpsertObjectParamBatches(params []storage.UpsertObjectParams, size int) [][]storage.UpsertObjectParams {
	if len(params) == 0 {
		return nil
	}
	if size <= 0 {
		size = len(params)
	}

	batches := [][]storage.UpsertObjectParams{}
	for start := 0; start < len(params); start += size {
		end := start + size
		if end > len(params) {
			end = len(params)
		}
		batches = append(batches, params[start:end])
	}

	return batches
}

func updateObjectMutationProgress(ctx context.Context, store *storage.Store, runID string, action string, phase string, total int, headed int, upserted int) error {
	progress := storage.JobRunPayload{
		"action":           action,
		"phase":            phase,
		"objects_total":    total,
		"objects_headed":   headed,
		"objects_upserted": upserted,
	}
	_, err := store.JobRuns().UpdateJobRunProgress(ctx, storage.UpdateJobRunProgressParams{
		ID:       runID,
		Progress: progress,
	})

	return err
}
