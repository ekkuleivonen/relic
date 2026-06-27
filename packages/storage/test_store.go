package storage

import "context"

func PrepareTestStore(ctx context.Context, store *Store) error {
	if err := SeedAttributeCatalog(ctx, store.AttributeCatalog()); err != nil {
		return err
	}
	if err := SeedUpstreamCaptureFields(ctx, store.UpstreamCaptureFields()); err != nil {
		return err
	}

	return nil
}
