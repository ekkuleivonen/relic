package storage

import (
	"context"
	"time"

	"github.com/ekkuleivonen/relic/packages/secrets"
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
	Provider             BucketProvider
	EndpointURL          string
	Region               string
	BucketName           string
	Prefix               string
	EncryptedCredentials secrets.Envelope
	PluginSettings       BucketPluginSettingsMap
	CreatedAt            time.Time
	UpdatedAt            time.Time
}

type BucketProvider string

const (
	BucketProviderS3 BucketProvider = "s3"
)

type BucketPluginSettingsMap map[string]BucketPluginSettings

type BucketPluginSettings struct {
	Enabled  bool           `json:"enabled"`
	Settings map[string]any `json:"settings"`
}

type CreateBucketParams struct {
	Name                 string
	Provider             BucketProvider
	EndpointURL          string
	Region               string
	BucketName           string
	Prefix               string
	EncryptedCredentials secrets.Envelope
	PluginSettings       BucketPluginSettingsMap
}

type ListBucketsParams struct {
	Provider BucketProvider
	Limit    int
	Offset   int
}

type UpdateBucketParams struct {
	ID                   string
	Name                 *string
	EndpointURL          *string
	Region               *string
	Prefix               *string
	EncryptedCredentials *secrets.Envelope
	PluginSettings       *BucketPluginSettingsMap
}

func (s *BucketStore) CreateBucket(ctx context.Context, params CreateBucketParams) (Bucket, error) {
	return Bucket{}, ErrNotImplemented
}

func (s *BucketStore) GetBucket(ctx context.Context, id string) (Bucket, error) {
	return Bucket{}, ErrNotImplemented
}

func (s *BucketStore) ListBuckets(ctx context.Context, params ListBucketsParams) ([]Bucket, error) {
	return nil, ErrNotImplemented
}

func (s *BucketStore) UpdateBucket(ctx context.Context, params UpdateBucketParams) (Bucket, error) {
	return Bucket{}, ErrNotImplemented
}

func (s *BucketStore) DeleteBucket(ctx context.Context, id string) error {
	return ErrNotImplemented
}
