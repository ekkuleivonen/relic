package storage

import (
	"context"

	"github.com/elei-io/pithosys/packages/search"
)

func (s *Store) EnsureConfigured() error {
	if s == nil || s.pool == nil {
		return ErrNilPool
	}

	return nil
}

func (s *Store) SearchPithosysQL(ctx context.Context, text string, scope SearchScope) ([]Object, error) {
	query, err := search.Parse(text)
	if err != nil {
		return nil, search.ValidationError(err)
	}
	if err := s.EnsureConfigured(); err != nil {
		return nil, err
	}

	bound, err := bindPithosysQL(ctx, s.AttributeCatalog(), query)
	if err != nil {
		return nil, err
	}

	return s.Objects().Search(ctx, bound, scope)
}
