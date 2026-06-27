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

type ObjectRepository interface {
	UpsertObject(context.Context, UpsertObjectParams) (Object, error)
	UpsertObjects(context.Context, []UpsertObjectParams) ([]Object, error)
	GetObject(context.Context, string) (Object, error)
	ListObjects(context.Context, ListObjectsParams) ([]Object, error)
	ListObjectsInScope(context.Context, ObjectScopeParams) ([]Object, error)
	CountObjectsInScope(context.Context, ObjectScopeParams) (int64, error)
	StreamObjectsInScope(context.Context, ObjectScopeParams, func(Object) error) error
	DeleteObject(context.Context, string) error
	DeleteObjects(context.Context, DeleteObjectsParams) (int64, error)
	DeleteObjectsNotSeenSince(context.Context, DeleteObjectsNotSeenSinceParams) (int64, error)
	Search(context.Context, search.BoundQuery, SearchScope) ([]Object, error)
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
	objects, err := s.UpsertObjects(ctx, []UpsertObjectParams{params})
	if err != nil {
		return Object{}, err
	}
	if len(objects) == 0 {
		return Object{}, ErrNotFound
	}

	return objects[0], nil
}

func (s *ObjectStore) UpsertObjects(ctx context.Context, params []UpsertObjectParams) ([]Object, error) {
	if len(params) == 0 {
		return []Object{}, nil
	}

	rowsJSON, err := encodeUpsertObjectRows(params)
	if err != nil {
		return nil, err
	}

	rows, err := s.runner.Query(ctx, `
		WITH input AS (
			SELECT *
			FROM jsonb_to_recordset($1::jsonb) AS x(
				ordinal int,
				id text,
				bucket_id text,
				key text,
				attributes jsonb,
				attribute_provenance jsonb
			)
		),
		upserted AS (
		INSERT INTO objects (
			id,
			bucket_id,
			key,
			attributes,
			attribute_provenance
		)
			SELECT
				id,
				bucket_id,
				key,
				attributes,
				attribute_provenance
			FROM input
			ORDER BY ordinal
		ON CONFLICT (bucket_id, key)
		DO UPDATE SET
			attributes = EXCLUDED.attributes || jsonb_build_object(
				'core',
				jsonb_build_object(
					'object_id', objects.id,
					'first_seen_at', COALESCE(
						objects.attributes #>> '{core,first_seen_at}',
						EXCLUDED.attributes #>> '{core,first_seen_at}'
					),
					'last_seen_at', EXCLUDED.attributes #>> '{core,last_seen_at}'
				)
			),
			attribute_provenance = EXCLUDED.attribute_provenance,
			updated_at = now()
		RETURNING
			id,
			bucket_id,
			key,
			attributes,
			attribute_provenance,
			created_at,
			updated_at
		)
		SELECT
			upserted.id,
			upserted.bucket_id,
			upserted.key,
			upserted.attributes,
			upserted.attribute_provenance,
			upserted.created_at,
			upserted.updated_at
		FROM upserted
		INNER JOIN input ON input.bucket_id = upserted.bucket_id
			AND input.key = upserted.key
		ORDER BY input.ordinal
	`, rowsJSON)
	if err != nil {
		return nil, fmt.Errorf("upsert objects: %w", err)
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
		return nil, fmt.Errorf("upsert objects: %w", err)
	}

	if err := observeAttributeCatalog(ctx, s.runner, params); err != nil {
		return nil, err
	}

	return objects, nil
}

func (s *ObjectStore) GetObject(ctx context.Context, id string) (Object, error) {
	return scanObject(s.runner.QueryRow(ctx, `
		SELECT
			id,
			bucket_id,
			key,
			attributes,
			attribute_provenance,
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
			attributes,
			attribute_provenance,
			created_at,
			updated_at
		FROM objects
		WHERE ($1 = '' OR bucket_id = $1)
			AND ($2 = '' OR key LIKE $2 || '%')
			AND ($3 = '' OR attributes #>> '{upstream,header,content_type}' = $3)
			AND ($4 = '' OR key ILIKE '%' || $4 || '%')
		ORDER BY bucket_id ASC, key ASC
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

func (s *ObjectStore) Search(ctx context.Context, bound search.BoundQuery, scope SearchScope) ([]Object, error) {
	compiled, err := CompileObjectsSearch(bound, scope)
	if err != nil {
		return nil, fmt.Errorf("search objects: %w", err)
	}

	rows, err := s.runner.Query(ctx, compiled.SQL, compiled.Args...)
	if err != nil {
		return nil, fmt.Errorf("search objects: %w", err)
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
		return nil, fmt.Errorf("search objects: %w", err)
	}

	return objects, nil
}

func (s *ObjectStore) ListObjectsInScope(ctx context.Context, params ObjectScopeParams) ([]Object, error) {
	objects := []Object{}
	err := s.StreamObjectsInScope(ctx, params, func(object Object) error {
		objects = append(objects, object)
		return nil
	})
	if err != nil {
		return nil, err
	}

	return objects, nil
}

func (s *ObjectStore) CountObjectsInScope(ctx context.Context, params ObjectScopeParams) (int64, error) {
	row := s.runner.QueryRow(ctx, `
		SELECT count(*)
		FROM objects
		WHERE ($1 = '' OR bucket_id = $1)
			AND ($2 = '' OR key LIKE $2 || '%')
	`, params.BucketID, params.Prefix)

	var count int64
	if err := row.Scan(&count); err != nil {
		return 0, fmt.Errorf("count objects in scope: %w", err)
	}

	return count, nil
}

func (s *ObjectStore) StreamObjectsInScope(ctx context.Context, params ObjectScopeParams, fn func(Object) error) error {
	if fn == nil {
		return fmt.Errorf("stream objects in scope: callback is required")
	}

	rows, err := s.runner.Query(ctx, `
		SELECT
			id,
			bucket_id,
			key,
			attributes,
			attribute_provenance,
			created_at,
			updated_at
		FROM objects
		WHERE ($1 = '' OR bucket_id = $1)
			AND ($2 = '' OR key LIKE $2 || '%')
		ORDER BY bucket_id ASC, key ASC
	`, params.BucketID, params.Prefix)
	if err != nil {
		return fmt.Errorf("stream objects in scope: %w", err)
	}
	defer rows.Close()

	for rows.Next() {
		object, err := scanObject(rows)
		if err != nil {
			return err
		}
		if err := fn(object); err != nil {
			return err
		}
	}
	if err := rows.Err(); err != nil {
		return fmt.Errorf("stream objects in scope: %w", err)
	}

	return nil
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
			AND (attributes #>> '{core,last_seen_at}')::timestamptz < $3
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
		&attributesBytes,
		&attributeProvenanceBytes,
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

	firstSeenAt, lastSeenAt, err := coreTimestamps(object.Attributes)
	if err != nil {
		return Object{}, err
	}
	object.FirstSeenAt = firstSeenAt
	object.LastSeenAt = lastSeenAt

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

type upsertObjectRow struct {
	Ordinal             int             `json:"ordinal"`
	ID                  string          `json:"id"`
	BucketID            string          `json:"bucket_id"`
	Key                 string          `json:"key"`
	Attributes          json.RawMessage `json:"attributes"`
	AttributeProvenance json.RawMessage `json:"attribute_provenance"`
}

func encodeUpsertObjectRows(params []UpsertObjectParams) ([]byte, error) {
	rows := make([]upsertObjectRow, 0, len(params))
	for index, param := range params {
		id, err := newObjectID()
		if err != nil {
			return nil, err
		}
		seenAt := time.Now().UTC()
		if param.SeenAt != nil {
			seenAt = param.SeenAt.UTC()
		}
		attributes := cloneObjectAttributes(param.Attributes)
		injectCoreAttributes(attributes, id, seenAt)
		encodedAttributes, err := encodeObjectAttributes(attributes)
		if err != nil {
			return nil, err
		}
		attributeProvenance, err := encodeObjectAttributeProvenance(param.AttributeProvenance)
		if err != nil {
			return nil, err
		}
		rows = append(rows, upsertObjectRow{
			Ordinal:             index,
			ID:                  id,
			BucketID:            param.BucketID,
			Key:                 param.Key,
			Attributes:          json.RawMessage(encodedAttributes),
			AttributeProvenance: json.RawMessage(attributeProvenance),
		})
	}

	encoded, err := json.Marshal(rows)
	if err != nil {
		return nil, fmt.Errorf("encode object upsert rows: %w", err)
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
