package storage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/ekkuleivonen/relic/packages/search"
	"github.com/jackc/pgx/v5"
)

type CollectionRepository interface {
	CreateCollection(context.Context, CreateCollectionParams) (Collection, error)
	GetCollection(context.Context, string) (Collection, error)
	ListCollections(context.Context, ListCollectionsParams) ([]Collection, error)
	UpdateCollection(context.Context, UpdateCollectionParams) (Collection, error)
	DeleteCollection(context.Context, string) error
}

type CollectionStore struct {
	runner Runner
}

func NewCollectionStore(runner Runner) *CollectionStore {
	return &CollectionStore{runner: runner}
}

type CollectionStatus string

const (
	CollectionStatusValidEnum   CollectionStatus = "valid"
	CollectionStatusInvalidEnum CollectionStatus = "invalid"
)

type Collection struct {
	ID              string
	Name            string
	Description     string
	QueryText       string
	QueryAST        json.RawMessage
	QueryVersion    string
	Dependencies    []searchDependency
	Status          CollectionStatus
	OwnerUserID     string
	CreatedByType   string
	CreatedByID     string
	CreatedByName   string
	CreatedByRunID  string
	CreatedAt       time.Time
	UpdatedAt       time.Time
}

type searchDependency struct {
	Kind string `json:"kind"`
	Name string `json:"name"`
	Type string `json:"type,omitempty"`
}

type CreateCollectionParams struct {
	Name           string
	Description    string
	QueryText      string
	QueryAST       json.RawMessage
	QueryVersion   string
	Dependencies   []searchDependency
	Status         CollectionStatus
	OwnerUserID    string
	CreatedByType  string
	CreatedByID    string
	CreatedByName  string
	CreatedByRunID string
}

type ListCollectionsParams struct {
	Limit  int
	Offset int
}

type UpdateCollectionParams struct {
	ID             string
	Name           *string
	Description    *string
	QueryText      *string
	QueryAST       json.RawMessage
	QueryVersion   *string
	Dependencies   []searchDependency
	Status         *CollectionStatus
	OwnerUserID    *string
	CreatedByType  *string
	CreatedByID    *string
	CreatedByName  *string
	CreatedByRunID *string
	UpdateQuery    bool
}

func (s *CollectionStore) CreateCollection(ctx context.Context, params CreateCollectionParams) (Collection, error) {
	id, err := newCollectionID()
	if err != nil {
		return Collection{}, err
	}

	status := params.Status
	if status == "" {
		status = CollectionStatusValidEnum
	}

	dependencies, err := encodeSearchDependencies(params.Dependencies)
	if err != nil {
		return Collection{}, err
	}

	return scanCollection(s.runner.QueryRow(ctx, `
		INSERT INTO collections (
			id,
			name,
			description,
			query_text,
			query_ast,
			query_version,
			dependencies,
			status,
			owner_user_id,
			created_by_type,
			created_by_id,
			created_by_name,
			created_by_run_id
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
		RETURNING
			id,
			name,
			description,
			query_text,
			query_ast,
			query_version,
			dependencies,
			status,
			owner_user_id,
			created_by_type,
			created_by_id,
			created_by_name,
			created_by_run_id,
			created_at,
			updated_at
	`, id,
		params.Name,
		params.Description,
		params.QueryText,
		params.QueryAST,
		params.QueryVersion,
		dependencies,
		string(status),
		nullString(params.OwnerUserID),
		nullString(params.CreatedByType),
		nullString(params.CreatedByID),
		nullString(params.CreatedByName),
		nullString(params.CreatedByRunID),
	))
}

func (s *CollectionStore) GetCollection(ctx context.Context, id string) (Collection, error) {
	return scanCollection(s.runner.QueryRow(ctx, `
		SELECT
			id,
			name,
			description,
			query_text,
			query_ast,
			query_version,
			dependencies,
			status,
			owner_user_id,
			created_by_type,
			created_by_id,
			created_by_name,
			created_by_run_id,
			created_at,
			updated_at
		FROM collections
		WHERE id = $1
	`, id))
}

func (s *CollectionStore) ListCollections(ctx context.Context, params ListCollectionsParams) ([]Collection, error) {
	limit := params.Limit
	if limit <= 0 {
		limit = 100
	}
	if limit > 500 {
		limit = 500
	}
	offset := params.Offset
	if offset < 0 {
		offset = 0
	}

	rows, err := s.runner.Query(ctx, `
		SELECT
			id,
			name,
			description,
			query_text,
			query_ast,
			query_version,
			dependencies,
			status,
			owner_user_id,
			created_by_type,
			created_by_id,
			created_by_name,
			created_by_run_id,
			created_at,
			updated_at
		FROM collections
		ORDER BY name ASC, created_at ASC
		LIMIT $1
		OFFSET $2
	`, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("list collections: %w", err)
	}
	defer rows.Close()

	return scanCollections(rows)
}

func (s *CollectionStore) UpdateCollection(ctx context.Context, params UpdateCollectionParams) (Collection, error) {
	current, err := s.GetCollection(ctx, params.ID)
	if err != nil {
		return Collection{}, err
	}

	name := current.Name
	if params.Name != nil {
		name = *params.Name
	}

	description := current.Description
	if params.Description != nil {
		description = *params.Description
	}

	queryText := current.QueryText
	queryAST := current.QueryAST
	queryVersion := current.QueryVersion
	dependencies := current.Dependencies
	status := current.Status

	if params.UpdateQuery {
		if params.QueryText == nil {
			return Collection{}, fmt.Errorf("update collection query: query text is required")
		}
		queryText = *params.QueryText
		queryAST = params.QueryAST
		if params.QueryVersion != nil {
			queryVersion = *params.QueryVersion
		}
		dependencies = params.Dependencies
		if params.Status != nil {
			status = *params.Status
		}
	}

	ownerUserID := current.OwnerUserID
	if params.OwnerUserID != nil {
		ownerUserID = *params.OwnerUserID
	}

	createdByType := current.CreatedByType
	if params.CreatedByType != nil {
		createdByType = *params.CreatedByType
	}
	createdByID := current.CreatedByID
	if params.CreatedByID != nil {
		createdByID = *params.CreatedByID
	}
	createdByName := current.CreatedByName
	if params.CreatedByName != nil {
		createdByName = *params.CreatedByName
	}
	createdByRunID := current.CreatedByRunID
	if params.CreatedByRunID != nil {
		createdByRunID = *params.CreatedByRunID
	}

	encodedDependencies, err := encodeSearchDependencies(dependencies)
	if err != nil {
		return Collection{}, err
	}

	return scanCollection(s.runner.QueryRow(ctx, `
		UPDATE collections
		SET
			name = $2,
			description = $3,
			query_text = $4,
			query_ast = $5,
			query_version = $6,
			dependencies = $7,
			status = $8,
			owner_user_id = $9,
			created_by_type = $10,
			created_by_id = $11,
			created_by_name = $12,
			created_by_run_id = $13,
			updated_at = now()
		WHERE id = $1
		RETURNING
			id,
			name,
			description,
			query_text,
			query_ast,
			query_version,
			dependencies,
			status,
			owner_user_id,
			created_by_type,
			created_by_id,
			created_by_name,
			created_by_run_id,
			created_at,
			updated_at
	`, params.ID,
		name,
		description,
		queryText,
		queryAST,
		queryVersion,
		encodedDependencies,
		string(status),
		nullString(ownerUserID),
		nullString(createdByType),
		nullString(createdByID),
		nullString(createdByName),
		nullString(createdByRunID),
	))
}

func (s *CollectionStore) DeleteCollection(ctx context.Context, id string) error {
	tag, err := s.runner.Exec(ctx, `DELETE FROM collections WHERE id = $1`, id)
	if err != nil {
		return fmt.Errorf("delete collection: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}

	return nil
}

func DependenciesFromSearch(dependencies []search.Dependency) []searchDependency {
	if len(dependencies) == 0 {
		return []searchDependency{}
	}

	encoded := make([]searchDependency, 0, len(dependencies))
	for _, dependency := range dependencies {
		item := searchDependency{
			Kind: string(dependency.Kind),
			Name: dependency.Name,
		}
		if dependency.Type != "" {
			item.Type = string(dependency.Type)
		}
		encoded = append(encoded, item)
	}

	return encoded
}

func encodeSearchDependencies(dependencies []searchDependency) ([]byte, error) {
	if dependencies == nil {
		dependencies = []searchDependency{}
	}

	encoded, err := json.Marshal(dependencies)
	if err != nil {
		return nil, fmt.Errorf("encode collection dependencies: %w", err)
	}

	return encoded, nil
}

func scanCollection(row pgx.Row) (Collection, error) {
	var collection Collection
	var queryAST []byte
	var dependencies []byte
	var status string
	var ownerUserID *string
	var createdByType *string
	var createdByID *string
	var createdByName *string
	var createdByRunID *string

	err := row.Scan(
		&collection.ID,
		&collection.Name,
		&collection.Description,
		&collection.QueryText,
		&queryAST,
		&collection.QueryVersion,
		&dependencies,
		&status,
		&ownerUserID,
		&createdByType,
		&createdByID,
		&createdByName,
		&createdByRunID,
		&collection.CreatedAt,
		&collection.UpdatedAt,
	)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return Collection{}, ErrNotFound
		}
		return Collection{}, fmt.Errorf("scan collection: %w", err)
	}

	collection.QueryAST = queryAST
	collection.Status = CollectionStatus(status)
	if ownerUserID != nil {
		collection.OwnerUserID = *ownerUserID
	}
	if createdByType != nil {
		collection.CreatedByType = *createdByType
	}
	if createdByID != nil {
		collection.CreatedByID = *createdByID
	}
	if createdByName != nil {
		collection.CreatedByName = *createdByName
	}
	if createdByRunID != nil {
		collection.CreatedByRunID = *createdByRunID
	}

	decodedDependencies, err := decodeSearchDependencies(dependencies)
	if err != nil {
		return Collection{}, err
	}
	collection.Dependencies = decodedDependencies

	return collection, nil
}

func scanCollections(rows pgx.Rows) ([]Collection, error) {
	collections := []Collection{}
	for rows.Next() {
		collection, err := scanCollection(rows)
		if err != nil {
			return nil, err
		}
		collections = append(collections, collection)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("scan collections: %w", err)
	}

	return collections, nil
}

func decodeSearchDependencies(data []byte) ([]searchDependency, error) {
	if len(data) == 0 {
		return []searchDependency{}, nil
	}

	var dependencies []searchDependency
	if err := json.Unmarshal(data, &dependencies); err != nil {
		return nil, fmt.Errorf("decode collection dependencies: %w", err)
	}

	return dependencies, nil
}

func newCollectionID() (string, error) {
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		return "", fmt.Errorf("generate collection id: %w", err)
	}

	return "collection_" + hex.EncodeToString(random), nil
}
