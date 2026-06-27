package storage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/jackc/pgx/v5"
)

type BucketRepository interface {
	CreateBucket(context.Context, CreateBucketParams) (Bucket, error)
	GetBucket(context.Context, string) (Bucket, error)
	ListBuckets(context.Context, ListBucketsParams) ([]Bucket, error)
	UpdateBucket(context.Context, UpdateBucketParams) (Bucket, error)
	DeleteBucket(context.Context, string) error
}

type BucketStore struct {
	runner Runner
}

func NewBucketStore(runner Runner) *BucketStore {
	return &BucketStore{runner: runner}
}

type Bucket struct {
	ID                   string
	Name                 string
	Upstream             BucketUpstream
	EndpointURL          string
	Region               string
	BucketName           string
	Prefix               string
	UpstreamConfig       BucketUpstreamConfig
	EncryptedCredentials secrets.Envelope
	RelicConfig          BucketRelicConfig
	CreatedAt            time.Time
	UpdatedAt            time.Time
}

type BucketUpstream string

const (
	BucketUpstreamS3 BucketUpstream = "s3"
)

type BucketUpstreamConfig map[string]any

type CreateBucketParams struct {
	Name                 string
	Upstream             BucketUpstream
	EndpointURL          string
	Region               string
	BucketName           string
	Prefix               string
	UpstreamConfig       BucketUpstreamConfig
	EncryptedCredentials secrets.Envelope
	RelicConfig          BucketRelicConfig
}

type ListBucketsParams struct {
	Upstream BucketUpstream
	Limit    int
	Offset   int
}

type UpdateBucketParams struct {
	ID                   string
	Name                 *string
	EndpointURL          *string
	Region               *string
	Prefix               *string
	UpstreamConfig       *BucketUpstreamConfig
	EncryptedCredentials *secrets.Envelope
	RelicConfig          *BucketRelicConfig
}

func (s *BucketStore) CreateBucket(ctx context.Context, params CreateBucketParams) (Bucket, error) {
	id, err := newBucketID()
	if err != nil {
		return Bucket{}, err
	}

	relicConfig, err := encodeRelicConfig(relicConfigForCreate(params.RelicConfig))
	if err != nil {
		return Bucket{}, err
	}
	upstreamConfig, err := encodeUpstreamConfig(params.UpstreamConfig)
	if err != nil {
		return Bucket{}, err
	}

	return scanBucket(s.runner.QueryRow(ctx, `
		INSERT INTO buckets (
			id,
			name,
			upstream,
			endpoint_url,
			region,
			bucket_name,
			prefix,
			upstream_config,
			credential_key_id,
			credential_algorithm,
			credential_nonce,
			credential_ciphertext,
			relic_config
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
		RETURNING
			id,
			name,
			upstream,
			endpoint_url,
			region,
			bucket_name,
			prefix,
			upstream_config,
			credential_key_id,
			credential_algorithm,
			credential_nonce,
			credential_ciphertext,
			relic_config,
			created_at,
			updated_at
	`, id,
		params.Name,
		string(params.Upstream),
		params.EndpointURL,
		params.Region,
		params.BucketName,
		params.Prefix,
		upstreamConfig,
		params.EncryptedCredentials.KeyID,
		params.EncryptedCredentials.Algorithm,
		params.EncryptedCredentials.Nonce,
		params.EncryptedCredentials.Ciphertext,
		relicConfig,
	))
}

func (s *BucketStore) GetBucket(ctx context.Context, id string) (Bucket, error) {
	return scanBucket(s.runner.QueryRow(ctx, `
		SELECT
			id,
			name,
			upstream,
			endpoint_url,
			region,
			bucket_name,
			prefix,
			upstream_config,
			credential_key_id,
			credential_algorithm,
			credential_nonce,
			credential_ciphertext,
			relic_config,
			created_at,
			updated_at
		FROM buckets
		WHERE id = $1
	`, id))
}

func (s *BucketStore) ListBuckets(ctx context.Context, params ListBucketsParams) ([]Bucket, error) {
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

	var (
		rows pgx.Rows
		err  error
	)
	if params.Upstream == "" {
		rows, err = s.runner.Query(ctx, `
			SELECT
				id,
				name,
				upstream,
				endpoint_url,
				region,
				bucket_name,
				prefix,
				upstream_config,
				credential_key_id,
				credential_algorithm,
				credential_nonce,
				credential_ciphertext,
				relic_config,
				created_at,
				updated_at
			FROM buckets
			ORDER BY created_at DESC, id DESC
			LIMIT $1 OFFSET $2
		`, limit, offset)
	} else {
		rows, err = s.runner.Query(ctx, `
			SELECT
				id,
				name,
				upstream,
				endpoint_url,
				region,
				bucket_name,
				prefix,
				upstream_config,
				credential_key_id,
				credential_algorithm,
				credential_nonce,
				credential_ciphertext,
				relic_config,
				created_at,
				updated_at
			FROM buckets
			WHERE upstream = $1
			ORDER BY created_at DESC, id DESC
			LIMIT $2 OFFSET $3
		`, string(params.Upstream), limit, offset)
	}
	if err != nil {
		return nil, fmt.Errorf("list buckets: %w", err)
	}
	defer rows.Close()

	buckets := []Bucket{}
	for rows.Next() {
		bucket, err := scanBucket(rows)
		if err != nil {
			return nil, err
		}
		buckets = append(buckets, bucket)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list buckets: %w", err)
	}

	return buckets, nil
}

func (s *BucketStore) UpdateBucket(ctx context.Context, params UpdateBucketParams) (Bucket, error) {
	var upstreamConfig *string
	if params.UpstreamConfig != nil {
		encoded, err := encodeUpstreamConfig(*params.UpstreamConfig)
		if err != nil {
			return Bucket{}, err
		}
		value := string(encoded)
		upstreamConfig = &value
	}

	var relicConfig *string
	if params.RelicConfig != nil {
		encoded, err := encodeRelicConfig(*params.RelicConfig)
		if err != nil {
			return Bucket{}, err
		}
		value := string(encoded)
		relicConfig = &value
	}

	var (
		credentialKeyID      *string
		credentialAlgorithm  *string
		credentialNonce      any
		credentialCiphertext any
	)
	if params.EncryptedCredentials != nil {
		credentialKeyID = &params.EncryptedCredentials.KeyID
		algorithm := string(params.EncryptedCredentials.Algorithm)
		credentialAlgorithm = &algorithm
		credentialNonce = params.EncryptedCredentials.Nonce
		credentialCiphertext = params.EncryptedCredentials.Ciphertext
	}

	return scanBucket(s.runner.QueryRow(ctx, `
		UPDATE buckets
		SET
			name = COALESCE($2, name),
			endpoint_url = COALESCE($3, endpoint_url),
			region = COALESCE($4, region),
			prefix = COALESCE($5, prefix),
			upstream_config = COALESCE($6::jsonb, upstream_config),
			credential_key_id = COALESCE($7, credential_key_id),
			credential_algorithm = COALESCE($8, credential_algorithm),
			credential_nonce = COALESCE($9::bytea, credential_nonce),
			credential_ciphertext = COALESCE($10::bytea, credential_ciphertext),
			relic_config = COALESCE($11::jsonb, relic_config),
			updated_at = now()
		WHERE id = $1
		RETURNING
			id,
			name,
			upstream,
			endpoint_url,
			region,
			bucket_name,
			prefix,
			upstream_config,
			credential_key_id,
			credential_algorithm,
			credential_nonce,
			credential_ciphertext,
			relic_config,
			created_at,
			updated_at
	`, params.ID,
		params.Name,
		params.EndpointURL,
		params.Region,
		params.Prefix,
		upstreamConfig,
		credentialKeyID,
		credentialAlgorithm,
		credentialNonce,
		credentialCiphertext,
		relicConfig,
	))
}

func (s *BucketStore) DeleteBucket(ctx context.Context, id string) error {
	tag, err := s.runner.Exec(ctx, "DELETE FROM buckets WHERE id = $1", id)
	if err != nil {
		return fmt.Errorf("delete bucket: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}

	return nil
}

func scanBucket(row pgx.Row) (Bucket, error) {
	var (
		bucket           Bucket
		upstream         string
		upstreamConfigBytes []byte
		relicConfigBytes []byte
	)

	err := row.Scan(
		&bucket.ID,
		&bucket.Name,
		&upstream,
		&bucket.EndpointURL,
		&bucket.Region,
		&bucket.BucketName,
		&bucket.Prefix,
		&upstreamConfigBytes,
		&bucket.EncryptedCredentials.KeyID,
		&bucket.EncryptedCredentials.Algorithm,
		&bucket.EncryptedCredentials.Nonce,
		&bucket.EncryptedCredentials.Ciphertext,
		&relicConfigBytes,
		&bucket.CreatedAt,
		&bucket.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return Bucket{}, ErrNotFound
	}
	if err != nil {
		return Bucket{}, fmt.Errorf("scan bucket: %w", err)
	}

	bucket.Upstream = BucketUpstream(upstream)
	if len(upstreamConfigBytes) == 0 {
		bucket.UpstreamConfig = BucketUpstreamConfig{}
	} else if err := json.Unmarshal(upstreamConfigBytes, &bucket.UpstreamConfig); err != nil {
		return Bucket{}, fmt.Errorf("decode bucket upstream config: %w", err)
	}
	if bucket.UpstreamConfig == nil {
		bucket.UpstreamConfig = BucketUpstreamConfig{}
	}

	if len(relicConfigBytes) == 0 {
		return bucket, nil
	}
	if err := json.Unmarshal(relicConfigBytes, &bucket.RelicConfig); err != nil {
		return Bucket{}, fmt.Errorf("decode bucket relic config: %w", err)
	}

	return bucket, nil
}

func encodeUpstreamConfig(config BucketUpstreamConfig) ([]byte, error) {
	if config == nil {
		config = BucketUpstreamConfig{}
	}

	encoded, err := json.Marshal(config)
	if err != nil {
		return nil, fmt.Errorf("encode bucket upstream config: %w", err)
	}

	return encoded, nil
}

func encodeRelicConfig(config BucketRelicConfig) ([]byte, error) {
	encoded, err := json.Marshal(config)
	if err != nil {
		return nil, fmt.Errorf("encode bucket relic config: %w", err)
	}

	return encoded, nil
}

func relicConfigForCreate(config BucketRelicConfig) BucketRelicConfig {
	if config.Scan.Enabled == nil && config.Scan.Interval == "" {
		return DefaultBucketRelicConfig()
	}

	return config
}

func newBucketID() (string, error) {
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		return "", fmt.Errorf("generate bucket id: %w", err)
	}

	return "bucket_" + hex.EncodeToString(random), nil
}
