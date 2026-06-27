package storage

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/ekkuleivonen/relic/packages/search"
	"github.com/jackc/pgx/v5"
)

type CatalogSource string

const (
	CatalogSourceBuiltin    CatalogSource = "builtin"
	CatalogSourceRegistered CatalogSource = "registered"
	CatalogSourceObserved   CatalogSource = "observed"
)

type CatalogEntry struct {
	Path        string
	ValueType   search.ValueType
	Source      CatalogSource
	FirstSeenAt time.Time
	UpdatedAt   time.Time
}

type AttributeCatalogRepository interface {
	Resolve(context.Context, string) (CatalogEntry, bool, error)
	List(context.Context) ([]CatalogEntry, error)
	SeedBuiltin(context.Context, []search.AttributeDefinition) error
	SeedRegistered(context.Context, []search.AttributeDefinition) error
	UpsertObserved(context.Context, string, search.ValueType) error
}

type AttributeCatalogStore struct {
	runner Runner
}

func NewAttributeCatalogStore(runner Runner) *AttributeCatalogStore {
	return &AttributeCatalogStore{runner: runner}
}

func (s *AttributeCatalogStore) Resolve(ctx context.Context, path string) (CatalogEntry, bool, error) {
	entry, err := scanCatalogEntry(s.runner.QueryRow(ctx, `
		SELECT path, value_type, source, first_seen_at, updated_at
		FROM attribute_catalog
		WHERE path = $1
	`, path))
	if errors.Is(err, pgx.ErrNoRows) {
		return CatalogEntry{}, false, nil
	}
	if err != nil {
		return CatalogEntry{}, false, fmt.Errorf("resolve attribute catalog path: %w", err)
	}

	return entry, true, nil
}

func (s *AttributeCatalogStore) List(ctx context.Context) ([]CatalogEntry, error) {
	if s == nil || s.runner == nil {
		return nil, ErrNilPool
	}

	rows, err := s.runner.Query(ctx, `
		SELECT path, value_type, source, first_seen_at, updated_at
		FROM attribute_catalog
		ORDER BY path ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("list attribute catalog: %w", err)
	}
	defer rows.Close()

	entries := []CatalogEntry{}
	for rows.Next() {
		entry, err := scanCatalogEntry(rows)
		if err != nil {
			return nil, err
		}
		entries = append(entries, entry)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list attribute catalog: %w", err)
	}

	return entries, nil
}

func (s *AttributeCatalogStore) SeedBuiltin(ctx context.Context, entries []search.AttributeDefinition) error {
	return s.seedDefinitions(ctx, entries, CatalogSourceBuiltin)
}

func (s *AttributeCatalogStore) SeedRegistered(ctx context.Context, entries []search.AttributeDefinition) error {
	return s.seedDefinitions(ctx, entries, CatalogSourceRegistered)
}

func (s *AttributeCatalogStore) UpsertObserved(ctx context.Context, path string, typ search.ValueType) error {
	if path == "" {
		return fmt.Errorf("upsert observed catalog path: path is required")
	}

	dbType, err := catalogValueTypeToDB(typ)
	if err != nil {
		return fmt.Errorf("upsert observed catalog path: %w", err)
	}

	existing, ok, err := s.Resolve(ctx, path)
	if err != nil {
		return err
	}
	if ok {
		switch existing.Source {
		case CatalogSourceBuiltin, CatalogSourceRegistered:
			return nil
		case CatalogSourceObserved:
			widened, compatible := widenCatalogValueType(existing.ValueType, typ)
			if !compatible {
				return ErrCatalogTypeConflict
			}
			if widened == existing.ValueType {
				_, err := s.runner.Exec(ctx, `
					UPDATE attribute_catalog
					SET updated_at = now()
					WHERE path = $1 AND source = 'observed'
				`, path)
				if err != nil {
					return fmt.Errorf("touch observed catalog path: %w", err)
				}
				return nil
			}

			widenedDB, err := catalogValueTypeToDB(widened)
			if err != nil {
				return fmt.Errorf("upsert observed catalog path: %w", err)
			}
			_, err = s.runner.Exec(ctx, `
				UPDATE attribute_catalog
				SET value_type = $2, updated_at = now()
				WHERE path = $1 AND source = 'observed'
			`, path, widenedDB)
			if err != nil {
				return fmt.Errorf("widen observed catalog path: %w", err)
			}
			return nil
		default:
			return fmt.Errorf("upsert observed catalog path: unsupported source %q", existing.Source)
		}
	}

	_, err = s.runner.Exec(ctx, `
		INSERT INTO attribute_catalog (path, value_type, source)
		VALUES ($1, $2, 'observed')
		ON CONFLICT (path) DO NOTHING
	`, path, dbType)
	if err != nil {
		return fmt.Errorf("insert observed catalog path: %w", err)
	}

	return nil
}

func (s *AttributeCatalogStore) seedDefinitions(ctx context.Context, entries []search.AttributeDefinition, source CatalogSource) error {
	if len(entries) == 0 {
		return nil
	}

	rowsJSON, err := encodeCatalogSeedRows(entries, source)
	if err != nil {
		return err
	}

	_, err = s.runner.Exec(ctx, `
		WITH input AS (
			SELECT *
			FROM jsonb_to_recordset($1::jsonb) AS x(
				path text,
				value_type text,
				source text
			)
		)
		INSERT INTO attribute_catalog (path, value_type, source)
		SELECT path, value_type, source
		FROM input
		ON CONFLICT (path) DO UPDATE SET
			value_type = EXCLUDED.value_type,
			source = EXCLUDED.source,
			updated_at = now()
		WHERE attribute_catalog.source IN ('builtin', 'registered')
			AND EXCLUDED.source IN ('builtin', 'registered')
	`, rowsJSON)
	if err != nil {
		return fmt.Errorf("seed attribute catalog (%s): %w", source, err)
	}

	return nil
}

type catalogSeedRow struct {
	Path      string `json:"path"`
	ValueType string `json:"value_type"`
	Source    string `json:"source"`
}

func encodeCatalogSeedRows(entries []search.AttributeDefinition, source CatalogSource) ([]byte, error) {
	rows := make([]catalogSeedRow, 0, len(entries))
	for _, entry := range entries {
		if entry.Path == "" {
			return nil, fmt.Errorf("encode catalog seed rows: path is required")
		}
		dbType, err := catalogValueTypeToDB(entry.Type)
		if err != nil {
			return nil, fmt.Errorf("encode catalog seed rows for path %q: %w", entry.Path, err)
		}
		rows = append(rows, catalogSeedRow{
			Path:      entry.Path,
			ValueType: dbType,
			Source:    string(source),
		})
	}

	encoded, err := json.Marshal(rows)
	if err != nil {
		return nil, fmt.Errorf("encode catalog seed rows: %w", err)
	}

	return encoded, nil
}

func scanCatalogEntry(row pgx.Row) (CatalogEntry, error) {
	var (
		entry       CatalogEntry
		valueType   string
		source      string
		firstSeenAt time.Time
		updatedAt   time.Time
	)

	err := row.Scan(&entry.Path, &valueType, &source, &firstSeenAt, &updatedAt)
	if err != nil {
		return CatalogEntry{}, fmt.Errorf("scan attribute catalog entry: %w", err)
	}

	entry.ValueType, err = catalogValueTypeFromDB(valueType)
	if err != nil {
		return CatalogEntry{}, err
	}
	entry.Source = CatalogSource(source)
	entry.FirstSeenAt = firstSeenAt
	entry.UpdatedAt = updatedAt

	return entry, nil
}
