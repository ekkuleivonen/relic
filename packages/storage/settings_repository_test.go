package storage

import (
	"context"
	"errors"
	"testing"
)

func TestSettingsStoreSeedIsIdempotent(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	settings := store.Settings()
	if err := SeedSettings(ctx, settings); err != nil {
		t.Fatalf("SeedSettings returned error: %v", err)
	}

	first, err := settings.List(ctx)
	if err != nil {
		t.Fatalf("List returned error: %v", err)
	}
	if len(first) != len(SettingDefinitions) {
		t.Fatalf("setting count = %d, want %d", len(first), len(SettingDefinitions))
	}

	if err := settings.Set(ctx, SettingWorkerRunnerPollInterval, "5s", "admin-user"); err != nil {
		t.Fatalf("Set returned error: %v", err)
	}

	if err := SeedSettings(ctx, settings); err != nil {
		t.Fatalf("SeedSettings second call returned error: %v", err)
	}

	got, err := settings.Get(ctx, SettingWorkerRunnerPollInterval)
	if err != nil {
		t.Fatalf("Get returned error: %v", err)
	}
	if got.Value != "5s" {
		t.Fatalf("Value = %q, want %q", got.Value, "5s")
	}
	if got.UpdatedBy == nil || *got.UpdatedBy != "admin-user" {
		t.Fatalf("UpdatedBy = %#v, want admin-user", got.UpdatedBy)
	}
}

func TestSettingsStoreSetRejectsUnknownKey(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	settings := store.Settings()
	if err := SeedSettings(ctx, settings); err != nil {
		t.Fatalf("SeedSettings returned error: %v", err)
	}

	err := settings.Set(ctx, "NOT_A_SETTING", "true", "admin-user")
	if !errors.Is(err, ErrSettingUnknown) {
		t.Fatalf("Set error = %v, want ErrSettingUnknown", err)
	}
}

func TestSettingsStoreSetRejectsInvalidDuration(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	settings := store.Settings()
	if err := SeedSettings(ctx, settings); err != nil {
		t.Fatalf("SeedSettings returned error: %v", err)
	}

	err := settings.Set(ctx, SettingWorkerRunnerPollInterval, "not-a-duration", "admin-user")
	if !errors.Is(err, ErrSettingInvalidValue) {
		t.Fatalf("Set error = %v, want ErrSettingInvalidValue", err)
	}
}

func TestSettingsStoreSetRejectsInvalidBool(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	settings := store.Settings()
	if err := SeedSettings(ctx, settings); err != nil {
		t.Fatalf("SeedSettings returned error: %v", err)
	}

	err := settings.Set(ctx, SettingScanBucketEnabled, "maybe", "admin-user")
	if !errors.Is(err, ErrSettingInvalidValue) {
		t.Fatalf("Set error = %v, want ErrSettingInvalidValue", err)
	}
}

func TestSettingsStoreSetUpdatesValue(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	settings := store.Settings()
	if err := SeedSettings(ctx, settings); err != nil {
		t.Fatalf("SeedSettings returned error: %v", err)
	}

	if err := settings.Set(ctx, SettingDuplicateDetectionEnabled, "true", "admin-1"); err != nil {
		t.Fatalf("Set returned error: %v", err)
	}

	got, err := settings.Get(ctx, SettingDuplicateDetectionEnabled)
	if err != nil {
		t.Fatalf("Get returned error: %v", err)
	}
	if got.Value != "true" {
		t.Fatalf("Value = %q, want true", got.Value)
	}
	if got.UpdatedBy == nil || *got.UpdatedBy != "admin-1" {
		t.Fatalf("UpdatedBy = %#v, want admin-1", got.UpdatedBy)
	}
}

func TestValidateSettingValueDurationMustBePositive(t *testing.T) {
	definition, ok := SettingDefinitionByKey(SettingWorkerRunnerPollInterval)
	if !ok {
		t.Fatal("SettingDefinitionByKey returned false")
	}

	if err := ValidateSettingValue(definition, "0s"); err == nil {
		t.Fatal("ValidateSettingValue returned nil error, want positive duration error")
	}
}
