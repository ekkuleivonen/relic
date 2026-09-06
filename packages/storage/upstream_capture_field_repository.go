package storage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"

	"github.com/elei-io/pithosys/packages/search"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

type UpstreamCaptureFieldRepository interface {
	List(context.Context) ([]UpstreamCaptureField, error)
	ListEnabled(context.Context) ([]UpstreamCaptureField, error)
	Get(context.Context, string) (UpstreamCaptureField, error)
	CreateUser(context.Context, CreateUpstreamCaptureFieldParams) (UpstreamCaptureField, error)
	Update(context.Context, string, UpdateUpstreamCaptureFieldParams) (UpstreamCaptureField, error)
	DeleteUser(context.Context, string) error
	SeedPlatform(context.Context, []UpstreamCaptureFieldSeed) error
}

type UpstreamCaptureFieldStore struct {
	runner Runner
}

func NewUpstreamCaptureFieldStore(runner Runner) *UpstreamCaptureFieldStore {
	return &UpstreamCaptureFieldStore{runner: runner}
}

func (s *UpstreamCaptureFieldStore) List(ctx context.Context) ([]UpstreamCaptureField, error) {
	if s == nil || s.runner == nil {
		return nil, ErrNilPool
	}

	rows, err := s.runner.Query(ctx, `
		SELECT id, attribute_path, enabled, category, origin, capture_source, extractor_type, extractor_ref, value_type, created_at, updated_at
		FROM upstream_capture_fields
		ORDER BY attribute_path ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("list upstream capture fields: %w", err)
	}
	defer rows.Close()

	return scanUpstreamCaptureFields(rows)
}

func (s *UpstreamCaptureFieldStore) ListEnabled(ctx context.Context) ([]UpstreamCaptureField, error) {
	if s == nil || s.runner == nil {
		return nil, ErrNilPool
	}

	rows, err := s.runner.Query(ctx, `
		SELECT id, attribute_path, enabled, category, origin, capture_source, extractor_type, extractor_ref, value_type, created_at, updated_at
		FROM upstream_capture_fields
		WHERE enabled = true
		ORDER BY attribute_path ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("list enabled upstream capture fields: %w", err)
	}
	defer rows.Close()

	return scanUpstreamCaptureFields(rows)
}

func (s *UpstreamCaptureFieldStore) Get(ctx context.Context, id string) (UpstreamCaptureField, error) {
	field, err := scanUpstreamCaptureField(s.runner.QueryRow(ctx, `
		SELECT id, attribute_path, enabled, category, origin, capture_source, extractor_type, extractor_ref, value_type, created_at, updated_at
		FROM upstream_capture_fields
		WHERE id = $1
	`, id))
	if errors.Is(err, pgx.ErrNoRows) {
		return UpstreamCaptureField{}, ErrCaptureFieldNotFound
	}
	if err != nil {
		return UpstreamCaptureField{}, fmt.Errorf("get upstream capture field: %w", err)
	}

	return field, nil
}

func (s *UpstreamCaptureFieldStore) CreateUser(ctx context.Context, params CreateUpstreamCaptureFieldParams) (UpstreamCaptureField, error) {
	if err := validateCreateUpstreamCaptureFieldParams(params); err != nil {
		return UpstreamCaptureField{}, err
	}

	id, err := newUpstreamCaptureFieldID()
	if err != nil {
		return UpstreamCaptureField{}, err
	}

	field, err := scanUpstreamCaptureField(s.runner.QueryRow(ctx, `
		INSERT INTO upstream_capture_fields (
			id, attribute_path, enabled, category, origin, capture_source, extractor_type, extractor_ref, value_type
		) VALUES (
			$1, $2, $3, $4, $5, $6, $7, $8, $9
		)
		RETURNING id, attribute_path, enabled, category, origin, capture_source, extractor_type, extractor_ref, value_type, created_at, updated_at
	`,
		id,
		strings.TrimSpace(params.AttributePath),
		params.Enabled,
		CaptureFieldCategoryOptional,
		CaptureFieldOriginUser,
		params.CaptureSource,
		params.ExtractorType,
		NormalizeCaptureExtractorRef(params.ExtractorType, params.ExtractorRef),
		params.ValueType,
	))
	if err != nil {
		return UpstreamCaptureField{}, mapCaptureFieldInsertError(err)
	}

	return field, nil
}

func (s *UpstreamCaptureFieldStore) Update(ctx context.Context, id string, params UpdateUpstreamCaptureFieldParams) (UpstreamCaptureField, error) {
	current, err := s.Get(ctx, id)
	if err != nil {
		return UpstreamCaptureField{}, err
	}

	if current.Origin == CaptureFieldOriginPlatform {
		if params.AttributePath != nil || params.CaptureSource != nil || params.ExtractorType != nil || params.ExtractorRef != nil || params.ValueType != nil {
			return UpstreamCaptureField{}, ErrCaptureFieldInvalidUpdate
		}
		if params.Enabled != nil && !*params.Enabled && current.Category == CaptureFieldCategoryRequired {
			return UpstreamCaptureField{}, ErrCaptureFieldRequired
		}
	} else {
		next := current
		if params.AttributePath != nil {
			if err := ValidateUpstreamCaptureAttributePath(*params.AttributePath); err != nil {
				return UpstreamCaptureField{}, err
			}
			next.AttributePath = strings.TrimSpace(*params.AttributePath)
		}
		if params.Enabled != nil {
			next.Enabled = *params.Enabled
		}
		if params.CaptureSource != nil {
			next.CaptureSource = *params.CaptureSource
		}
		if params.ExtractorType != nil {
			next.ExtractorType = *params.ExtractorType
		}
		if params.ExtractorRef != nil {
			next.ExtractorRef = NormalizeCaptureExtractorRef(next.ExtractorType, *params.ExtractorRef)
		}
		if params.ValueType != nil {
			next.ValueType = *params.ValueType
		}
		if err := ValidateUpstreamCaptureExtractor(next.ExtractorType, next.ExtractorRef, CaptureFieldOriginUser); err != nil {
			return UpstreamCaptureField{}, err
		}
		if next.Enabled == false && next.Category == CaptureFieldCategoryRequired {
			return UpstreamCaptureField{}, ErrCaptureFieldRequired
		}

		field, err := scanUpstreamCaptureField(s.runner.QueryRow(ctx, `
			UPDATE upstream_capture_fields
			SET attribute_path = $2,
			    enabled = $3,
			    capture_source = $4,
			    extractor_type = $5,
			    extractor_ref = $6,
			    value_type = $7,
			    updated_at = now()
			WHERE id = $1
			RETURNING id, attribute_path, enabled, category, origin, capture_source, extractor_type, extractor_ref, value_type, created_at, updated_at
		`, id, next.AttributePath, next.Enabled, next.CaptureSource, next.ExtractorType, next.ExtractorRef, next.ValueType))
		if err != nil {
			return UpstreamCaptureField{}, mapCaptureFieldInsertError(err)
		}

		return field, nil
	}

	if params.Enabled == nil {
		return current, nil
	}

	field, err := scanUpstreamCaptureField(s.runner.QueryRow(ctx, `
		UPDATE upstream_capture_fields
		SET enabled = $2,
		    updated_at = now()
		WHERE id = $1
		RETURNING id, attribute_path, enabled, category, origin, capture_source, extractor_type, extractor_ref, value_type, created_at, updated_at
	`, id, *params.Enabled))
	if err != nil {
		return UpstreamCaptureField{}, fmt.Errorf("update upstream capture field: %w", err)
	}

	return field, nil
}

func (s *UpstreamCaptureFieldStore) DeleteUser(ctx context.Context, id string) error {
	current, err := s.Get(ctx, id)
	if err != nil {
		return err
	}
	if current.Origin == CaptureFieldOriginPlatform {
		return ErrCaptureFieldPlatformOnly
	}

	tag, err := s.runner.Exec(ctx, `DELETE FROM upstream_capture_fields WHERE id = $1`, id)
	if err != nil {
		return fmt.Errorf("delete upstream capture field: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrCaptureFieldNotFound
	}

	return nil
}

func (s *UpstreamCaptureFieldStore) SeedPlatform(ctx context.Context, seeds []UpstreamCaptureFieldSeed) error {
	for _, seed := range seeds {
		_, err := s.runner.Exec(ctx, `
			INSERT INTO upstream_capture_fields (
				id, attribute_path, enabled, category, origin, capture_source, extractor_type, extractor_ref, value_type
			) VALUES (
				$1, $2, $3, $4, $5, $6, $7, $8, $9
			)
			ON CONFLICT (id) DO UPDATE SET
				attribute_path = EXCLUDED.attribute_path,
				category = EXCLUDED.category,
				capture_source = EXCLUDED.capture_source,
				extractor_type = EXCLUDED.extractor_type,
				extractor_ref = EXCLUDED.extractor_ref,
				value_type = EXCLUDED.value_type,
				updated_at = now()
			WHERE upstream_capture_fields.origin = 'platform'
		`,
			seed.ID,
			seed.AttributePath,
			seed.Enabled,
			seed.Category,
			CaptureFieldOriginPlatform,
			seed.CaptureSource,
			seed.ExtractorType,
			NormalizeCaptureExtractorRef(seed.ExtractorType, seed.ExtractorRef),
			seed.ValueType,
		)
		if err != nil {
			return fmt.Errorf("seed upstream capture field %q: %w", seed.ID, err)
		}
	}

	return nil
}

func validateCreateUpstreamCaptureFieldParams(params CreateUpstreamCaptureFieldParams) error {
	if err := ValidateUpstreamCaptureAttributePath(params.AttributePath); err != nil {
		return err
	}
	if err := ValidateUpstreamCaptureExtractor(params.ExtractorType, params.ExtractorRef, CaptureFieldOriginUser); err != nil {
		return err
	}
	if params.ValueType == "" {
		return fmt.Errorf("value_type is required")
	}

	switch params.CaptureSource {
	case CaptureSourceHead, CaptureSourceTagging:
	default:
		return fmt.Errorf("unsupported capture_source %q", params.CaptureSource)
	}

	return nil
}

func mapCaptureFieldInsertError(err error) error {
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == "23505" {
		return ErrCaptureFieldConflict
	}

	return fmt.Errorf("upsert upstream capture field: %w", err)
}

func newUpstreamCaptureFieldID() (string, error) {
	var raw [8]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", fmt.Errorf("generate upstream capture field id: %w", err)
	}

	return "capture_" + hex.EncodeToString(raw[:]), nil
}

type captureFieldScanner interface {
	Scan(dest ...any) error
}

func scanUpstreamCaptureField(row captureFieldScanner) (UpstreamCaptureField, error) {
	var field UpstreamCaptureField
	var category string
	var origin string
	var captureSource string
	var extractorType string
	var valueType string

	if err := row.Scan(
		&field.ID,
		&field.AttributePath,
		&field.Enabled,
		&category,
		&origin,
		&captureSource,
		&extractorType,
		&field.ExtractorRef,
		&valueType,
		&field.CreatedAt,
		&field.UpdatedAt,
	); err != nil {
		return UpstreamCaptureField{}, err
	}

	field.Category = CaptureFieldCategory(category)
	field.Origin = CaptureFieldOrigin(origin)
	field.CaptureSource = CaptureSource(captureSource)
	field.ExtractorType = CaptureExtractorType(extractorType)
	field.ValueType = search.ValueType(valueType)

	return field, nil
}

func scanUpstreamCaptureFields(rows pgx.Rows) ([]UpstreamCaptureField, error) {
	fields := []UpstreamCaptureField{}
	for rows.Next() {
		field, err := scanUpstreamCaptureField(rows)
		if err != nil {
			return nil, fmt.Errorf("scan upstream capture field: %w", err)
		}
		fields = append(fields, field)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("scan upstream capture fields: %w", err)
	}

	return fields, nil
}
