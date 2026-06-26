package storage

import (
	"context"
	"fmt"

	"github.com/ekkuleivonen/relic/packages/search"
)

func SeedAttributeCatalog(ctx context.Context, catalog *AttributeCatalogStore) error {
	if catalog == nil {
		return fmt.Errorf("seed attribute catalog: catalog store is required")
	}

	if err := catalog.SeedBuiltin(ctx, search.BuiltinAttributeDefinitions()); err != nil {
		return err
	}
	if err := catalog.SeedRegistered(ctx, search.RegisteredAttributeDefinitions()); err != nil {
		return err
	}

	return nil
}
