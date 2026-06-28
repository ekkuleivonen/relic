package storage

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
)

type SettingsRepository interface {
	List(context.Context) ([]Setting, error)
	Get(context.Context, string) (Setting, error)
	Set(context.Context, string, string, string) error
	Seed(context.Context) error
}

type SettingsStore struct {
	runner Runner
}

func NewSettingsStore(runner Runner) *SettingsStore {
	return &SettingsStore{runner: runner}
}

func (s *SettingsStore) List(ctx context.Context) ([]Setting, error) {
	rows, err := s.runner.Query(ctx, `
		SELECT key, value, encrypted, updated_at, updated_by
		FROM settings
		ORDER BY key ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("list settings: %w", err)
	}
	defer rows.Close()

	return scanSettings(rows)
}

func (s *SettingsStore) Get(ctx context.Context, key string) (Setting, error) {
	return scanSetting(s.runner.QueryRow(ctx, `
		SELECT key, value, encrypted, updated_at, updated_by
		FROM settings
		WHERE key = $1
	`, key))
}

func (s *SettingsStore) Set(ctx context.Context, key, value, updatedBy string) error {
	definition, ok := SettingDefinitionByKey(key)
	if !ok {
		return ErrSettingUnknown
	}
	if err := ValidateSettingValue(definition, value); err != nil {
		return fmt.Errorf("%w: %v", ErrSettingInvalidValue, err)
	}

	var updatedByArg any
	if updatedBy != "" {
		updatedByArg = updatedBy
	}

	tag, err := s.runner.Exec(ctx, `
		UPDATE settings
		SET
			value = $2,
			updated_at = now(),
			updated_by = $3
		WHERE key = $1
	`, key, value, updatedByArg)
	if err != nil {
		return fmt.Errorf("set setting %q: %w", key, err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}

	return nil
}

func (s *SettingsStore) Seed(ctx context.Context) error {
	for _, definition := range SettingDefinitions {
		_, err := s.runner.Exec(ctx, `
			INSERT INTO settings (key, value, encrypted)
			VALUES ($1, $2, $3)
			ON CONFLICT (key) DO NOTHING
		`, definition.Key, definition.Default, definition.Encrypted)
		if err != nil {
			return fmt.Errorf("seed setting %q: %w", definition.Key, err)
		}
	}

	return nil
}

func scanSetting(row pgx.Row) (Setting, error) {
	var setting Setting

	err := row.Scan(
		&setting.Key,
		&setting.Value,
		&setting.Encrypted,
		&setting.UpdatedAt,
		&setting.UpdatedBy,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return Setting{}, ErrNotFound
	}
	if err != nil {
		return Setting{}, fmt.Errorf("scan setting: %w", err)
	}

	return setting, nil
}

func scanSettings(rows pgx.Rows) ([]Setting, error) {
	settings := make([]Setting, 0)

	for rows.Next() {
		var setting Setting
		if err := rows.Scan(
			&setting.Key,
			&setting.Value,
			&setting.Encrypted,
			&setting.UpdatedAt,
			&setting.UpdatedBy,
		); err != nil {
			return nil, fmt.Errorf("scan settings: %w", err)
		}

		settings = append(settings, setting)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate settings: %w", err)
	}

	return settings, nil
}
