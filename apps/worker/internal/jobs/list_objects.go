package jobs

import (
	"context"
	"fmt"

	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

type ObjectListBudget interface {
	Allow(count int) bool
	Record(count int)
	ObjectsListed() int64
}

type ListCheckpoint struct {
	ContinuationToken string
	Marker            string
	ObjectsListed     int64
}

type ListObjectsPageProgress struct {
	PageObjects   []s3compat.ListedObject
	ObjectsListed int64
	Checkpoint    ListCheckpoint
	ListingComplete bool
}

type ListAllObjectsOptions struct {
	Client      s3compat.ObjectClient
	BucketName  string
	Prefix      string
	BucketLabel string
	Budget      ObjectListBudget
	Start       ListCheckpoint
	Filter      func(s3compat.ListedObject) bool
	OnObject    func(s3compat.ListedObject) error
	OnPage      func(progress ListObjectsPageProgress) error
}

func ListAllObjects(ctx context.Context, options ListAllObjectsOptions) (complete bool, objectsListed int64, err error) {
	if options.Client == nil {
		return false, 0, fmt.Errorf("list all objects: client is required")
	}
	if options.OnObject == nil {
		return false, 0, fmt.Errorf("list all objects: on object callback is required")
	}

	bucketLabel := options.BucketLabel
	if bucketLabel == "" {
		bucketLabel = options.BucketName
	}

	continuationToken := options.Start.ContinuationToken
	marker := options.Start.Marker
	objectsListed = options.Start.ObjectsListed

	for {
		page, err := options.Client.ListObjects(ctx, s3compat.ListObjectsInput{
			Bucket:            options.BucketName,
			Prefix:            options.Prefix,
			ContinuationToken: continuationToken,
			Marker:            marker,
		})
		if err != nil {
			return false, objectsListed, err
		}

		pageObjects := []s3compat.ListedObject{}
		for _, listedObject := range page.Objects {
			if options.Filter != nil && !options.Filter(listedObject) {
				continue
			}
			if options.Budget != nil && !options.Budget.Allow(1) {
				return false, objectsListed, nil
			}
			if err := options.OnObject(listedObject); err != nil {
				return false, objectsListed, err
			}
			if options.Budget != nil {
				options.Budget.Record(1)
			}
			objectsListed++
			pageObjects = append(pageObjects, listedObject)
		}

		listingComplete := !page.IsTruncated
		nextContinuationToken := page.NextContinuationToken
		nextMarker := page.NextMarker
		if !listingComplete && nextContinuationToken == "" && nextMarker == "" {
			return false, objectsListed, fmt.Errorf("list all objects %q: truncated page did not include a continuation token or marker", bucketLabel)
		}

		if options.OnPage != nil {
			if err := options.OnPage(ListObjectsPageProgress{
				PageObjects:     pageObjects,
				ObjectsListed:   objectsListed,
				ListingComplete: listingComplete,
				Checkpoint: ListCheckpoint{
					ContinuationToken: nextContinuationToken,
					Marker:            nextMarker,
					ObjectsListed:     objectsListed,
				},
			}); err != nil {
				return false, objectsListed, err
			}
		}

		if listingComplete {
			return true, objectsListed, nil
		}
		if options.Budget != nil && !options.Budget.Allow(0) {
			return false, objectsListed, nil
		}

		continuationToken = nextContinuationToken
		marker = nextMarker
	}
}
