package sync_bucket

import (
	"context"

	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/verification"
)

func collectLocalObjectsInScope(
	ctx context.Context,
	objects storage.ObjectRepository,
	scope storage.ObjectScopeParams,
	partition *verification.Partition,
) ([]storage.Object, error) {
	if partition == nil {
		return objects.ListObjectsInScope(ctx, scope)
	}

	localObjects := []storage.Object{}
	if err := objects.StreamObjectsInScope(ctx, scope, func(object storage.Object) error {
		if KeyMatchesPartition(object.Key, *partition) {
			localObjects = append(localObjects, object)
		}
		return nil
	}); err != nil {
		return nil, err
	}

	return localObjects, nil
}
