package storage

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Runner interface {
	Exec(context.Context, string, ...any) (pgconn.CommandTag, error)
	Query(context.Context, string, ...any) (pgx.Rows, error)
	QueryRow(context.Context, string, ...any) pgx.Row
}

type Store struct {
	pool *pgxpool.Pool
}

func New(pool *pgxpool.Pool) (*Store, error) {
	if pool == nil {
		return nil, ErrNilPool
	}

	return &Store{pool: pool}, nil
}

func (s *Store) Buckets() *BucketStore {
	return NewBucketStore(s.pool)
}

func (s *Store) JobRuns() *JobRunStore {
	return NewJobRunStore(s.pool)
}

func (s *Store) Objects() *ObjectStore {
	return NewObjectStore(s.pool)
}

func (s *Store) AttributeCatalog() *AttributeCatalogStore {
	return NewAttributeCatalogStore(s.pool)
}

func (s *Store) UpstreamCaptureFields() *UpstreamCaptureFieldStore {
	return NewUpstreamCaptureFieldStore(s.pool)
}

func (s *Store) UpstreamEvents() *UpstreamEventStore {
	return NewUpstreamEventStore(s.pool)
}

func (s *Store) Relations() *RelationStore {
	return NewRelationStore(s.pool)
}

func (s *Store) ListSearchRelationTypes(ctx context.Context) ([]string, error) {
	return s.Relations().ListRelationTypes(ctx)
}

func (s *Store) WithTx(ctx context.Context, fn func(context.Context, *Tx) error) error {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return fmt.Errorf("begin transaction: %w", err)
	}

	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()

	if err := fn(ctx, &Tx{tx: tx}); err != nil {
		return err
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit transaction: %w", err)
	}
	committed = true
	return nil
}

type Tx struct {
	tx pgx.Tx
}

func (tx *Tx) Buckets() *BucketStore {
	return NewBucketStore(tx.tx)
}

func (tx *Tx) JobRuns() *JobRunStore {
	return NewJobRunStore(tx.tx)
}

func (tx *Tx) Objects() *ObjectStore {
	return NewObjectStore(tx.tx)
}

func (tx *Tx) UpstreamEvents() *UpstreamEventStore {
	return NewUpstreamEventStore(tx.tx)
}

func (tx *Tx) AttributeCatalog() *AttributeCatalogStore {
	return NewAttributeCatalogStore(tx.tx)
}

func (tx *Tx) UpstreamCaptureFields() *UpstreamCaptureFieldStore {
	return NewUpstreamCaptureFieldStore(tx.tx)
}

func (tx *Tx) Relations() *RelationStore {
	return NewRelationStore(tx.tx)
}
