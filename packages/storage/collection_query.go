package storage

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/ekkuleivonen/relic/packages/search"
)

const CollectionStatusValid = "valid"

type PreparedCollectionQuery struct {
	AST          json.RawMessage
	QueryVersion string
	Dependencies []search.Dependency
	Status       string
}

func PrepareCollectionQuery(ctx context.Context, catalog *AttributeCatalogStore, queryText string) (PreparedCollectionQuery, error) {
	bound, err := ValidateRelicQL(ctx, catalog, queryText)
	if err != nil {
		return PreparedCollectionQuery{}, err
	}

	ast, err := search.MarshalQuery(bound.Query)
	if err != nil {
		return PreparedCollectionQuery{}, fmt.Errorf("prepare collection query: %w", err)
	}

	return PreparedCollectionQuery{
		AST:          ast,
		QueryVersion: bound.Query.Version,
		Dependencies: bound.Dependencies,
		Status:       CollectionStatusValid,
	}, nil
}
