package storage

import (
	"context"
	"fmt"
)

func SeedUpstreamCaptureFields(ctx context.Context, store *UpstreamCaptureFieldStore) error {
	if store == nil {
		return fmt.Errorf("seed upstream capture fields: store is required")
	}

	return store.SeedPlatform(ctx, PlatformUpstreamCaptureFields())
}
