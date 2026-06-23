package storage

import (
	"context"
	"errors"
	"fmt"

	"github.com/golang-migrate/migrate/v4"
	_ "github.com/golang-migrate/migrate/v4/database/postgres"
	_ "github.com/golang-migrate/migrate/v4/source/file"
)

const DefaultMigrationSourceURL = "file://packages/storage/migrations"

func RunMigrations(ctx context.Context, databaseURL string, sourceURL string) error {
	if err := ctx.Err(); err != nil {
		return err
	}

	if databaseURL == "" {
		return fmt.Errorf("database URL is required")
	}
	if sourceURL == "" {
		sourceURL = DefaultMigrationSourceURL
	}

	migrator, err := migrate.New(sourceURL, databaseURL)
	if err != nil {
		return fmt.Errorf("create migrator: %w", err)
	}
	defer func() {
		_, _ = migrator.Close()
	}()

	if err := migrator.Up(); err != nil && !errors.Is(err, migrate.ErrNoChange) {
		return fmt.Errorf("run migrations: %w", err)
	}

	return ctx.Err()
}
