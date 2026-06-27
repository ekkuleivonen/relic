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
	"time"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	importobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/import_objects"
	refreshobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/refresh_objects"
	removeobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/remove_objects"
	scanbucket "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/scan_bucket"
	scanscheduler "github.com/ekkuleivonen/relic/apps/worker/internal/scheduler"
	syncbucket "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/sync_bucket"
	workerRunner "github.com/ekkuleivonen/relic/apps/worker/internal/runner"
	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

const defaultPollInterval = 2 * time.Second

type config struct {
	DatabaseURL              string
	WorkerID                 string
	PollInterval             time.Duration
	EncryptionKeyID          string
	EncryptionKey            []byte
	ScanSchedulerEnabled     bool
	ScanSchedulerInterval    time.Duration
	ScanDefaultInterval      time.Duration
	ScanStagger              time.Duration
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
	registry, err := jobs.NewRegistry(syncBucketHandler, scanBucketHandler, importObjectsHandler, refreshObjectsHandler, removeObjectsHandler)
	if err != nil {
		return err
	}
	jobRunner, err := workerRunner.New(workerRunner.Options{
		Store:        store,
		Registry:     registry,
		WorkerID:     cfg.WorkerID,
		PollInterval: cfg.PollInterval,
		Logger:       slog.Default(),
	})
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	errCh := make(chan error, 2)

	go func() {
		slog.Info("worker started", "worker_id", cfg.WorkerID, "poll_interval", cfg.PollInterval)
		errCh <- jobRunner.Run(ctx)
	}()

	if cfg.ScanSchedulerEnabled {
		scanScheduler, err := scanscheduler.NewScanScheduler(scanscheduler.ScanSchedulerOptions{
			Store:             store,
			Logger:            slog.Default(),
			SchedulerInterval: cfg.ScanSchedulerInterval,
			DefaultInterval:   cfg.ScanDefaultInterval,
			Stagger:           cfg.ScanStagger,
		})
		if err != nil {
			return err
		}

		go func() {
			slog.Info(
				"scan scheduler started",
				"scheduler_interval", cfg.ScanSchedulerInterval,
				"default_scan_interval", cfg.ScanDefaultInterval,
				"stagger", cfg.ScanStagger,
			)
			errCh <- scanScheduler.Run(ctx)
		}()
	}

	running := 1
	if cfg.ScanSchedulerEnabled {
		running = 2
	}

	var runErr error
	for i := 0; i < running; i++ {
		if err := <-errCh; err != nil && !errors.Is(err, context.Canceled) {
			runErr = err
		}
	}

	if runErr != nil {
		return runErr
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

	pollInterval, err := durationEnv(lookup, "WORKER_POLL_INTERVAL", defaultPollInterval)
	if err != nil {
		return config{}, err
	}
	schedulerInterval, err := durationEnv(lookup, "SCAN_SCHEDULER_INTERVAL", pollInterval)
	if err != nil {
		return config{}, err
	}
	scanDefaultInterval, err := durationEnv(lookup, "SCAN_DEFAULT_INTERVAL", storage.DefaultScanInterval)
	if err != nil {
		return config{}, err
	}
	scanStagger, err := durationEnv(lookup, "SCAN_STAGGER", 30*time.Second)
	if err != nil {
		return config{}, err
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
		DatabaseURL:           databaseURL,
		WorkerID:              stringEnv(lookup, "WORKER_ID", defaultWorkerID()),
		PollInterval:          pollInterval,
		EncryptionKeyID:       encryptionKeyID,
		EncryptionKey:         encryptionKey,
		ScanSchedulerEnabled:  boolEnv(lookup, "SCAN_SCHEDULER_ENABLED", true),
		ScanSchedulerInterval: schedulerInterval,
		ScanDefaultInterval:   scanDefaultInterval,
		ScanStagger:           scanStagger,
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

func durationEnv(lookup lookupFunc, key string, fallback time.Duration) (time.Duration, error) {
	value, ok := lookup(key)
	if !ok || value == "" {
		return fallback, nil
	}

	parsed, err := time.ParseDuration(value)
	if err != nil {
		return 0, fmt.Errorf("parse %s: %w", key, err)
	}

	return parsed, nil
}

func boolEnv(lookup lookupFunc, key string, fallback bool) bool {
	value, ok := lookup(key)
	if !ok || value == "" {
		return fallback
	}

	switch strings.ToLower(strings.TrimSpace(value)) {
	case "1", "true", "t", "yes", "y", "on":
		return true
	case "0", "false", "f", "no", "n", "off":
		return false
	default:
		return fallback
	}
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
