package storage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

const RelationTypeDuplicate = "duplicate"

type RelationRepository interface {
	CreateRelation(context.Context, CreateRelationParams) (Relation, error)
	DeleteDuplicateRelationsBetween(context.Context, DeleteDuplicateRelationsBetweenParams) (int64, error)
	ListDuplicateRelationsBetween(context.Context, ListDuplicateRelationsBetweenParams) ([]Relation, error)
	ListRelationTypes(context.Context) ([]string, error)
}

type RelationStore struct {
	runner Runner
}

func NewRelationStore(runner Runner) *RelationStore {
	return &RelationStore{runner: runner}
}

type Relation struct {
	ID              string
	SourceObjectID  string
	TargetObjectID  string
	RelationType    string
	Attributes      RelationAttributes
	CreatedByType   string
	CreatedByID     string
	CreatedByName   string
	CreatedByRunID  string
	CreatedAt       time.Time
	UpdatedAt       time.Time
}

type RelationAttributes map[string]any

type CreateRelationParams struct {
	SourceObjectID string
	TargetObjectID string
	RelationType   string
	Attributes     RelationAttributes
	CreatedByType  string
	CreatedByID    string
	CreatedByName  string
	CreatedByRunID string
}

type DeleteDuplicateRelationsBetweenParams struct {
	ObjectIDs []string
}

type ListDuplicateRelationsBetweenParams struct {
	ObjectIDs []string
}

func (s *RelationStore) CreateRelation(ctx context.Context, params CreateRelationParams) (Relation, error) {
	if params.SourceObjectID == "" || params.TargetObjectID == "" {
		return Relation{}, fmt.Errorf("create relation: source and target object ids are required")
	}
	if params.SourceObjectID == params.TargetObjectID {
		return Relation{}, fmt.Errorf("create relation: source and target must differ")
	}
	relationType := params.RelationType
	if relationType == "" {
		relationType = RelationTypeDuplicate
	}

	id, err := newRelationID()
	if err != nil {
		return Relation{}, err
	}
	attributes, err := encodeRelationAttributes(params.Attributes)
	if err != nil {
		return Relation{}, err
	}

	row := s.runner.QueryRow(ctx, `
		INSERT INTO relations (
			id,
			source_object_id,
			target_object_id,
			relation_type,
			attributes,
			created_by_type,
			created_by_id,
			created_by_name,
			created_by_run_id
		) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
		ON CONFLICT (source_object_id, target_object_id, relation_type) DO UPDATE
		SET
			attributes = EXCLUDED.attributes,
			created_by_run_id = EXCLUDED.created_by_run_id,
			updated_at = now()
		RETURNING
			id,
			source_object_id,
			target_object_id,
			relation_type,
			attributes,
			created_by_type,
			created_by_id,
			created_by_name,
			created_by_run_id,
			created_at,
			updated_at
	`, id, params.SourceObjectID, params.TargetObjectID, relationType, attributes,
		nullString(params.CreatedByType),
		nullString(params.CreatedByID),
		nullString(params.CreatedByName),
		nullString(params.CreatedByRunID),
	)

	return scanRelation(row)
}

func (s *RelationStore) DeleteDuplicateRelationsBetween(ctx context.Context, params DeleteDuplicateRelationsBetweenParams) (int64, error) {
	if len(params.ObjectIDs) == 0 {
		return 0, nil
	}

	tag, err := s.runner.Exec(ctx, `
		DELETE FROM relations
		WHERE relation_type = $1
			AND source_object_id = ANY($2)
			AND target_object_id = ANY($2)
	`, RelationTypeDuplicate, params.ObjectIDs)
	if err != nil {
		return 0, fmt.Errorf("delete duplicate relations between objects: %w", err)
	}

	return tag.RowsAffected(), nil
}

func (s *RelationStore) ListDuplicateRelationsBetween(ctx context.Context, params ListDuplicateRelationsBetweenParams) ([]Relation, error) {
	if len(params.ObjectIDs) == 0 {
		return []Relation{}, nil
	}

	rows, err := s.runner.Query(ctx, `
		SELECT
			id,
			source_object_id,
			target_object_id,
			relation_type,
			attributes,
			created_by_type,
			created_by_id,
			created_by_name,
			created_by_run_id,
			created_at,
			updated_at
		FROM relations
		WHERE relation_type = $1
			AND source_object_id = ANY($2)
			AND target_object_id = ANY($2)
		ORDER BY created_at ASC
	`, RelationTypeDuplicate, params.ObjectIDs)
	if err != nil {
		return nil, fmt.Errorf("list duplicate relations between objects: %w", err)
	}
	defer rows.Close()

	relations := []Relation{}
	for rows.Next() {
		relation, err := scanRelation(rows)
		if err != nil {
			return nil, err
		}
		relations = append(relations, relation)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list duplicate relations between objects: %w", err)
	}

	return relations, nil
}

func (s *RelationStore) ListRelationTypes(ctx context.Context) ([]string, error) {
	rows, err := s.runner.Query(ctx, `
		SELECT DISTINCT relation_type
		FROM relations
		ORDER BY relation_type ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("list relation types: %w", err)
	}
	defer rows.Close()

	types := []string{}
	for rows.Next() {
		var relationType string
		if err := rows.Scan(&relationType); err != nil {
			return nil, fmt.Errorf("list relation types: %w", err)
		}
		types = append(types, relationType)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list relation types: %w", err)
	}

	return types, nil
}

func scanRelation(row pgx.Row) (Relation, error) {
	var (
		relation         Relation
		attributesBytes  []byte
		createdByType    *string
		createdByID      *string
		createdByName    *string
		createdByRunID   *string
	)

	err := row.Scan(
		&relation.ID,
		&relation.SourceObjectID,
		&relation.TargetObjectID,
		&relation.RelationType,
		&attributesBytes,
		&createdByType,
		&createdByID,
		&createdByName,
		&createdByRunID,
		&relation.CreatedAt,
		&relation.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return Relation{}, ErrNotFound
	}
	if err != nil {
		return Relation{}, fmt.Errorf("scan relation: %w", err)
	}
	if err := decodeRelationAttributes(attributesBytes, &relation.Attributes); err != nil {
		return Relation{}, err
	}
	if createdByType != nil {
		relation.CreatedByType = *createdByType
	}
	if createdByID != nil {
		relation.CreatedByID = *createdByID
	}
	if createdByName != nil {
		relation.CreatedByName = *createdByName
	}
	if createdByRunID != nil {
		relation.CreatedByRunID = *createdByRunID
	}

	return relation, nil
}

func encodeRelationAttributes(attributes RelationAttributes) ([]byte, error) {
	if attributes == nil {
		attributes = RelationAttributes{}
	}

	encoded, err := json.Marshal(attributes)
	if err != nil {
		return nil, fmt.Errorf("encode relation attributes: %w", err)
	}

	return encoded, nil
}

func decodeRelationAttributes(data []byte, target *RelationAttributes) error {
	if len(data) == 0 {
		*target = RelationAttributes{}
		return nil
	}
	if err := json.Unmarshal(data, target); err != nil {
		return fmt.Errorf("decode relation attributes: %w", err)
	}
	if *target == nil {
		*target = RelationAttributes{}
	}

	return nil
}

func newRelationID() (string, error) {
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		return "", fmt.Errorf("generate relation id: %w", err)
	}

	return "relation_" + hex.EncodeToString(random), nil
}

func nullString(value string) any {
	if value == "" {
		return nil
	}

	return value
}
