package jobs

import (
	"context"
	"fmt"
	"sync"

	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/upstreams/s3compat"
)

type HeadObjectFunc func(context.Context, ObjectEvidence) (storage.ObjectAttributes, error)

type HeadObjectResult struct {
	Evidence   ObjectEvidence
	Attributes storage.ObjectAttributes
}

func HeadObjects(ctx context.Context, objects []ObjectEvidence, concurrency int, head HeadObjectFunc) ([]HeadObjectResult, error) {
	if len(objects) == 0 {
		return []HeadObjectResult{}, nil
	}
	if concurrency <= 0 {
		concurrency = 1
	}
	if concurrency > len(objects) {
		concurrency = len(objects)
	}

	parentCtx := ctx
	ctx, cancel := context.WithCancel(ctx)
	defer cancel()

	type workItem struct {
		index    int
		evidence ObjectEvidence
	}

	work := make(chan workItem)
	results := make([]HeadObjectResult, len(objects))
	var (
		wg      sync.WaitGroup
		errOnce sync.Once
		headErr error
	)

	for worker := 0; worker < concurrency; worker++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for item := range work {
				attributes, err := head(ctx, item.evidence)
				if err != nil {
					errOnce.Do(func() {
						headErr = err
						cancel()
					})
					continue
				}
				results[item.index] = HeadObjectResult{
					Evidence:   item.evidence,
					Attributes: AttributesWithEvidence(attributes, item.evidence),
				}
			}
		}()
	}

	for index, evidence := range objects {
		select {
		case <-ctx.Done():
			break
		case work <- workItem{index: index, evidence: evidence}:
		}
		if ctx.Err() != nil {
			break
		}
	}
	close(work)
	wg.Wait()

	if headErr != nil {
		return nil, fmt.Errorf("head objects: %w", headErr)
	}
	if err := parentCtx.Err(); err != nil {
		return nil, err
	}

	return results, nil
}

func HeadObjectFuncForClient(client s3compat.ObjectClient, bucketName string, fields []storage.UpstreamCaptureField) HeadObjectFunc {
	return func(ctx context.Context, object ObjectEvidence) (storage.ObjectAttributes, error) {
		return s3compat.FetchCatalogAttributes(ctx, client, s3compat.HeadObjectInput{
			Bucket:    bucketName,
			Key:       object.Key,
			VersionID: object.VersionID,
		}, fields)
	}
}
