package storage

import (
	"context"
	"fmt"

	"github.com/ekkuleivonen/relic/packages/search"
)

func BuildSearchRegistry(ctx context.Context, catalog *AttributeCatalogStore) (search.Registry, error) {
	if catalog == nil {
		return nil, fmt.Errorf("build search registry: catalog store is required")
	}

	entries, err := catalog.List(ctx)
	if err != nil {
		return nil, err
	}

	attributes := make([]search.AttributeDefinition, 0, len(entries))
	for _, entry := range entries {
		attributes = append(attributes, search.AttributeDefinition{
			Path: entry.Path,
			Type: entry.ValueType,
		})
	}

	return search.NewStaticRegistry(search.BuiltinTargetDefinitions(), attributes), nil
}

func ValidateRelicQL(ctx context.Context, catalog *AttributeCatalogStore, text string) (search.BoundQuery, error) {
	query, err := search.Parse(text)
	if err != nil {
		return search.BoundQuery{}, search.ValidationError(err)
	}

	return bindRelicQL(ctx, catalog, query)
}

func bindRelicQL(ctx context.Context, catalog *AttributeCatalogStore, query search.Query) (search.BoundQuery, error) {
	registry, err := BuildSearchRegistry(ctx, catalog)
	if err != nil {
		return search.BoundQuery{}, err
	}

	bound, err := search.Bind(query, registry)
	if err != nil {
		return search.BoundQuery{}, search.ValidationError(err)
	}

	return bound, nil
}
