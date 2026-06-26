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

type ObjectRepository interface {
	UpsertObject(context.Context, UpsertObjectParams) (Object, error)
	GetObject(context.Context, string) (Object, error)
	ListObjects(context.Context, ListObjectsParams) ([]Object, error)
	ListObjectsInScope(context.Context, ObjectScopeParams) ([]Object, error)
	DeleteObject(context.Context, string) error
	DeleteObjects(context.Context, DeleteObjectsParams) (int64, error)
	DeleteObjectsNotSeenSince(context.Context, DeleteObjectsNotSeenSinceParams) (int64, error)
}

type ObjectStore struct {
	runner Runner
}

func NewObjectStore(runner Runner) *ObjectStore {
	return &ObjectStore{runner: runner}
}

type ObjectAttributes map[string]any

type ObjectAttributeProvenance map[string]string

type Object struct {
	ID                  string
	BucketID            string
	Key                 string
	VersionID           string
	Attributes          ObjectAttributes
	AttributeProvenance ObjectAttributeProvenance
	FirstSeenAt         time.Time
	LastSeenAt          time.Time
	CreatedAt           time.Time
	UpdatedAt           time.Time
}

type UpsertObjectParams struct {
	BucketID            string
	Key                 string
	VersionID           string
	Attributes          ObjectAttributes
	AttributeProvenance ObjectAttributeProvenance
	SeenAt              *time.Time
}

type ListObjectsParams struct {
	BucketID    string
	Prefix      string
	ContentType string
	KeyContains string
	Limit       int
	Offset      int
}

type DeleteObjectsNotSeenSinceParams struct {
	BucketID string
	Prefix   string
	SeenAt   time.Time
}

type ObjectScopeParams struct {
	BucketID string
	Prefix   string
}

type DeleteObjectsParams struct {
	IDs []string
}

func (s *ObjectStore) UpsertObject(ctx context.Context, params UpsertObjectParams) (Object, error) {
	id, err := newObjectID()
	if err != nil {
		return Object{}, err
	}

	attributes, err := encodeObjectAttributes(params.Attributes)
	if err != nil {
		return Object{}, err
	}
	attributeProvenance, err := encodeObjectAttributeProvenance(params.AttributeProvenance)
	if err != nil {
		return Object{}, err
	}

	return scanObject(s.runner.QueryRow(ctx, `
		INSERT INTO objects (
			id,
			bucket_id,
			key,
			version_id,
			attributes,
			attribute_provenance,
			first_seen_at,
			last_seen_at
		)
		VALUES ($1, $2, $3, $4, $5, $6, COALESCE($7::timestamptz, now()), COALESCE($7::timestamptz, now()))
		ON CONFLICT (bucket_id, key, version_id)
		DO UPDATE SET
			attributes = EXCLUDED.attributes,
			attribute_provenance = EXCLUDED.attribute_provenance,
			last_seen_at = EXCLUDED.last_seen_at,
			updated_at = now()
		RETURNING
			id,
			bucket_id,
			key,
			version_id,
			attributes,
			attribute_provenance,
			first_seen_at,
			last_seen_at,
			created_at,
			updated_at
	`, id,
		params.BucketID,
		params.Key,
		params.VersionID,
		attributes,
		attributeProvenance,
		params.SeenAt,
	))
}

func (s *ObjectStore) GetObject(ctx context.Context, id string) (Object, error) {
	return scanObject(s.runner.QueryRow(ctx, `
		SELECT
			id,
			bucket_id,
			key,
			version_id,
			attributes,
			attribute_provenance,
			first_seen_at,
			last_seen_at,
			created_at,
			updated_at
		FROM objects
		WHERE id = $1
	`, id))
}

func (s *ObjectStore) ListObjects(ctx context.Context, params ListObjectsParams) ([]Object, error) {
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
			bucket_id,
			key,
			version_id,
			attributes,
			attribute_provenance,
			first_seen_at,
			last_seen_at,
			created_at,
			updated_at
		FROM objects
		WHERE ($1 = '' OR bucket_id = $1)
			AND ($2 = '' OR key LIKE $2 || '%')
			AND ($3 = '' OR attributes #>> '{upstream,header,content_type}' = $3)
			AND ($4 = '' OR key ILIKE '%' || $4 || '%')
		ORDER BY bucket_id ASC, key ASC, version_id ASC
		LIMIT $5 OFFSET $6
	`, params.BucketID, params.Prefix, params.ContentType, params.KeyContains, limit, offset)
	if err != nil {
		return nil, fmt.Errorf("list objects: %w", err)
	}
	defer rows.Close()

	objects := []Object{}
	for rows.Next() {
		object, err := scanObject(rows)
		if err != nil {
			return nil, err
		}
		objects = append(objects, object)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list objects: %w", err)
	}

	return objects, nil
}

func (s *ObjectStore) ListObjectsInScope(ctx context.Context, params ObjectScopeParams) ([]Object, error) {
	rows, err := s.runner.Query(ctx, `
		SELECT
			id,
			bucket_id,
			key,
			version_id,
			attributes,
			attribute_provenance,
			first_seen_at,
			last_seen_at,
			created_at,
			updated_at
		FROM objects
		WHERE ($1 = '' OR bucket_id = $1)
			AND ($2 = '' OR key LIKE $2 || '%')
		ORDER BY bucket_id ASC, key ASC, version_id ASC
	`, params.BucketID, params.Prefix)
	if err != nil {
		return nil, fmt.Errorf("list objects in scope: %w", err)
	}
	defer rows.Close()

	objects := []Object{}
	for rows.Next() {
		object, err := scanObject(rows)
		if err != nil {
			return nil, err
		}
		objects = append(objects, object)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list objects in scope: %w", err)
	}

	return objects, nil
}

func (s *ObjectStore) DeleteObject(ctx context.Context, id string) error {
	tag, err := s.runner.Exec(ctx, "DELETE FROM objects WHERE id = $1", id)
	if err != nil {
		return fmt.Errorf("delete object: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}

	return nil
}

func (s *ObjectStore) DeleteObjects(ctx context.Context, params DeleteObjectsParams) (int64, error) {
	if len(params.IDs) == 0 {
		return 0, nil
	}

	tag, err := s.runner.Exec(ctx, "DELETE FROM objects WHERE id = ANY($1)", params.IDs)
	if err != nil {
		return 0, fmt.Errorf("delete objects: %w", err)
	}

	return tag.RowsAffected(), nil
}

func (s *ObjectStore) DeleteObjectsNotSeenSince(ctx context.Context, params DeleteObjectsNotSeenSinceParams) (int64, error) {
	tag, err := s.runner.Exec(ctx, `
		DELETE FROM objects
		WHERE bucket_id = $1
			AND ($2 = '' OR key LIKE $2 || '%')
			AND last_seen_at < $3
	`, params.BucketID, params.Prefix, params.SeenAt)
	if err != nil {
		return 0, fmt.Errorf("delete objects not seen since: %w", err)
	}

	return tag.RowsAffected(), nil
}

func scanObject(row pgx.Row) (Object, error) {
	var (
		object                   Object
		attributesBytes          []byte
		attributeProvenanceBytes []byte
	)

	err := row.Scan(
		&object.ID,
		&object.BucketID,
		&object.Key,
		&object.VersionID,
		&attributesBytes,
		&attributeProvenanceBytes,
		&object.FirstSeenAt,
		&object.LastSeenAt,
		&object.CreatedAt,
		&object.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return Object{}, ErrNotFound
	}
	if err != nil {
		return Object{}, fmt.Errorf("scan object: %w", err)
	}

	if err := decodeObjectAttributes(attributesBytes, &object.Attributes); err != nil {
		return Object{}, fmt.Errorf("decode object attributes: %w", err)
	}
	if err := decodeObjectAttributeProvenance(attributeProvenanceBytes, &object.AttributeProvenance); err != nil {
		return Object{}, fmt.Errorf("decode object attribute provenance: %w", err)
	}

	return object, nil
}

func encodeObjectAttributes(attributes ObjectAttributes) ([]byte, error) {
	if attributes == nil {
		attributes = ObjectAttributes{}
	}

	encoded, err := json.Marshal(attributes)
	if err != nil {
		return nil, fmt.Errorf("encode object attributes: %w", err)
	}

	return encoded, nil
}

func encodeObjectAttributeProvenance(provenance ObjectAttributeProvenance) ([]byte, error) {
	if provenance == nil {
		provenance = ObjectAttributeProvenance{}
	}

	encoded, err := json.Marshal(provenance)
	if err != nil {
		return nil, fmt.Errorf("encode object attribute provenance: %w", err)
	}

	return encoded, nil
}

func decodeObjectAttributes(data []byte, target *ObjectAttributes) error {
	if len(data) == 0 {
		*target = ObjectAttributes{}
		return nil
	}
	if err := json.Unmarshal(data, target); err != nil {
		return err
	}
	if *target == nil {
		*target = ObjectAttributes{}
	}

	return nil
}

func decodeObjectAttributeProvenance(data []byte, target *ObjectAttributeProvenance) error {
	if len(data) == 0 {
		*target = ObjectAttributeProvenance{}
		return nil
	}
	if err := json.Unmarshal(data, target); err != nil {
		return err
	}
	if *target == nil {
		*target = ObjectAttributeProvenance{}
	}

	return nil
}

func newObjectID() (string, error) {
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		return "", fmt.Errorf("generate object id: %w", err)
	}

	return "object_" + hex.EncodeToString(random), nil
}
