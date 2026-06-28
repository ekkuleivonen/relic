package storage

import (
	"context"
	"fmt"
)

func SeedSettings(ctx context.Context, store *SettingsStore) error {
	if store == nil {
		return fmt.Errorf("seed settings: store is required")
	}

	return store.Seed(ctx)
}
