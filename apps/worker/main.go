package main

import (
	"bufio"
	"context"
	"encoding/base64"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	detectduplicates "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/detect_duplicates"
	importobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/import_objects"
	refreshobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/refresh_objects"
	removeobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/remove_objects"
	scanbucket "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/scan_bucket"
	syncbucket "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/sync_bucket"
	"github.com/ekkuleivonen/relic/apps/worker/internal/supervisor"
	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

type config struct {
	DatabaseURL     string
	WorkerID        string
	EncryptionKeyID string
	EncryptionKey   []byte
}

func main() {
	if err := run(); err != nil {
		slog.Error("worker exited", "error", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := loadConfig()
	if err != nil {
		return err
	}

	ctx := context.Background()
	if err := storage.RunMigrations(ctx, cfg.DatabaseURL, ""); err != nil {
		return err
	}
	slog.Info("database migrations complete")

	database, err := db.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer database.Close()
	slog.Info("database connected")

	store, err := storage.New(database)
	if err != nil {
		return err
	}
	if err := storage.SeedAttributeCatalog(ctx, store.AttributeCatalog()); err != nil {
		return err
	}
	slog.Info("attribute catalog seeded")

	if err := storage.SeedUpstreamCaptureFields(ctx, store.UpstreamCaptureFields()); err != nil {
		return err
	}
	slog.Info("upstream capture fields seeded")

	if err := storage.SeedSettings(ctx, store.Settings()); err != nil {
		return err
	}
	slog.Info("settings seeded")

	secretManager, err := secrets.NewStaticKeyManager(cfg.EncryptionKeyID, cfg.EncryptionKey)
	if err != nil {
		return err
	}

	syncBucketHandler, err := syncbucket.NewHandler(syncbucket.HandlerOptions{
		Store:   store,
		Secrets: secretManager,
		Factory: s3compat.ClientFactory{},
	})
	if err != nil {
		return err
	}
	importObjectsHandler, err := importobjects.NewHandler(importobjects.HandlerOptions{
		Store:   store,
		Secrets: secretManager,
		Factory: s3compat.ClientFactory{},
	})
	if err != nil {
		return err
	}
	refreshObjectsHandler, err := refreshobjects.NewHandler(refreshobjects.HandlerOptions{
		Store:   store,
		Secrets: secretManager,
		Factory: s3compat.ClientFactory{},
	})
	if err != nil {
		return err
	}
	removeObjectsHandler, err := removeobjects.NewHandler(removeobjects.HandlerOptions{
		Store: store,
	})
	if err != nil {
		return err
	}
	scanBucketHandler, err := scanbucket.NewHandler(scanbucket.HandlerOptions{
		Store:   store,
		Secrets: secretManager,
		Factory: s3compat.ClientFactory{},
	})
	if err != nil {
		return err
	}
	detectDuplicatesHandler, err := detectduplicates.NewHandler(detectduplicates.HandlerOptions{
		Store:   store,
		Secrets: secretManager,
		Factory: s3compat.ClientFactory{},
	})
	if err != nil {
		return err
	}
	registry, err := jobs.NewRegistry(syncBucketHandler, scanBucketHandler, importObjectsHandler, refreshObjectsHandler, removeObjectsHandler, detectDuplicatesHandler)
	if err != nil {
		return err
	}

	workerSupervisor, err := supervisor.New(supervisor.Options{
		Store:    store,
		Registry: registry,
		WorkerID: cfg.WorkerID,
		Logger:   slog.Default(),
	})
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	slog.Info("worker started", "worker_id", cfg.WorkerID)
	if err := workerSupervisor.Run(ctx); err != nil && !errors.Is(err, context.Canceled) {
		return err
	}

	slog.Info("worker stopped")
	return nil
}

func loadConfig() (config, error) {
	fileEnv, err := loadDotEnv(".env")
	if err != nil {
		return config{}, err
	}

	lookup := func(key string) (string, bool) {
		if value, ok := os.LookupEnv(key); ok {
			return value, true
		}

		value, ok := fileEnv[key]
		return value, ok
	}

	databaseURL := stringEnv(lookup, "DATABASE_URL", "")
	if databaseURL == "" {
		return config{}, fmt.Errorf("DATABASE_URL is required")
	}

	encryptionKeyBase64 := stringEnv(lookup, "ENCRYPTION_KEY_BASE64", "")
	if encryptionKeyBase64 == "" {
		return config{}, fmt.Errorf("ENCRYPTION_KEY_BASE64 is required")
	}
	encryptionKey, err := base64.StdEncoding.DecodeString(encryptionKeyBase64)
	if err != nil {
		return config{}, fmt.Errorf("parse ENCRYPTION_KEY_BASE64: %w", err)
	}
	encryptionKeyID := stringEnv(lookup, "ENCRYPTION_KEY_ID", "")
	if encryptionKeyID == "" {
		return config{}, fmt.Errorf("ENCRYPTION_KEY_ID is required")
	}

	return config{
		DatabaseURL:     databaseURL,
		WorkerID:        stringEnv(lookup, "WORKER_ID", defaultWorkerID()),
		EncryptionKeyID: encryptionKeyID,
		EncryptionKey:   encryptionKey,
	}, nil
}

type lookupFunc func(string) (string, bool)

func stringEnv(lookup lookupFunc, key string, fallback string) string {
	value, ok := lookup(key)
	if !ok || value == "" {
		return fallback
	}

	return value
}

func defaultWorkerID() string {
	hostname, err := os.Hostname()
	if err != nil || hostname == "" {
		hostname = "worker"
	}

	return fmt.Sprintf("%s-%d", hostname, os.Getpid())
}

func loadDotEnv(path string) (map[string]string, error) {
	file, err := os.Open(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return map[string]string{}, nil
		}

		return nil, err
	}
	defer file.Close()

	values := map[string]string{}
	scanner := bufio.NewScanner(file)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}

		key, value, ok := strings.Cut(line, "=")
		if !ok {
			return nil, fmt.Errorf("parse %s: invalid line %q", path, line)
		}

		key = strings.TrimSpace(key)
		value = strings.TrimSpace(value)
		value = strings.Trim(value, `"'`)

		if key == "" {
			return nil, fmt.Errorf("parse %s: empty key", path)
		}

		values[key] = value
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

	return values, nil
}
