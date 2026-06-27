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
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	detectduplicates "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/detect_duplicates"
	importobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/import_objects"
	refreshobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/refresh_objects"
	removeobjects "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/remove_objects"
	scanbucket "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/scan_bucket"
	syncbucket "github.com/ekkuleivonen/relic/apps/worker/internal/jobs/sync_bucket"
	workerRunner "github.com/ekkuleivonen/relic/apps/worker/internal/runner"
	scanscheduler "github.com/ekkuleivonen/relic/apps/worker/internal/scheduler"
	jetstreamconsumer "github.com/ekkuleivonen/relic/apps/worker/internal/jetstreamconsumer"
	upstreamprocessor "github.com/ekkuleivonen/relic/apps/worker/internal/upstreamprocessor"
	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
	"github.com/ekkuleivonen/relic/packages/upstreams/s3compat"
)

const (
	defaultPollInterval                = 2 * time.Second
	defaultBatchLatency                = 30 * time.Second
	defaultConfigRefetchInterval       = 5 * time.Minute
	defaultDuplicateDetectionInterval  = 24 * time.Hour
)

type config struct {
	DatabaseURL                 string
	WorkerID                    string
	PollInterval                time.Duration
	BatchLatency                time.Duration
	ConfigRefetchInterval       time.Duration
	EncryptionKeyID             string
	EncryptionKey               []byte
	DuplicateDetectionEnabled   bool
	DuplicateDetectionInterval  time.Duration
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
	jobRunner, err := workerRunner.New(workerRunner.Options{
		Store:        store,
		Registry:     registry,
		WorkerID:     cfg.WorkerID,
		PollInterval: cfg.PollInterval,
		RetryDelay:   cfg.BatchLatency,
		Logger:       slog.Default(),
	})
	if err != nil {
		return err
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	errCh := make(chan error, 5)
	running := 4

	go func() {
		slog.Info(
			"worker started",
			"worker_id", cfg.WorkerID,
			"poll_interval", cfg.PollInterval,
			"batch_latency", cfg.BatchLatency,
			"config_refetch_interval", cfg.ConfigRefetchInterval,
		)
		errCh <- jobRunner.Run(ctx)
	}()

	scanScheduler, err := scanscheduler.NewScanScheduler(scanscheduler.ScanSchedulerOptions{
		Store:             store,
		Logger:            slog.Default(),
		SchedulerInterval: cfg.PollInterval,
		DefaultInterval:   storage.DefaultScanInterval,
		Stagger:           cfg.BatchLatency,
	})
	if err != nil {
		return err
	}

	go func() {
		slog.Info(
			"scan scheduler started",
			"poll_interval", cfg.PollInterval,
			"default_scan_interval", storage.DefaultScanInterval,
			"batch_latency", cfg.BatchLatency,
		)
		errCh <- scanScheduler.Run(ctx)
	}()

	if cfg.DuplicateDetectionEnabled {
		running++
		duplicateDetectionScheduler, err := scanscheduler.NewDuplicateDetectionScheduler(scanscheduler.DuplicateDetectionSchedulerOptions{
			Store:             store,
			Logger:            slog.Default(),
			SchedulerInterval: cfg.PollInterval,
			Interval:          cfg.DuplicateDetectionInterval,
		})
		if err != nil {
			return err
		}

		go func() {
			slog.Info(
				"duplicate detection scheduler started",
				"poll_interval", cfg.PollInterval,
				"duplicate_detection_interval", cfg.DuplicateDetectionInterval,
			)
			errCh <- duplicateDetectionScheduler.Run(ctx)
		}()
	} else {
		slog.Info("duplicate detection scheduler disabled")
	}

	upstreamProcessor, err := upstreamprocessor.NewProcessor(upstreamprocessor.ProcessorOptions{
		Store:             store,
		Logger:            slog.Default(),
		ProcessorInterval: cfg.PollInterval,
	})
	if err != nil {
		return err
	}

	go func() {
		slog.Info(
			"upstream event processor started",
			"poll_interval", cfg.PollInterval,
		)
		errCh <- upstreamProcessor.Run(ctx)
	}()

	jetstreamManager, err := jetstreamconsumer.NewManager(jetstreamconsumer.ManagerOptions{
		Store:                 store,
		Logger:                slog.Default(),
		ConfigRefetchInterval: cfg.ConfigRefetchInterval,
	})
	if err != nil {
		return err
	}

	go func() {
		slog.Info(
			"jetstream consumer manager started",
			"config_refetch_interval", cfg.ConfigRefetchInterval,
		)
		errCh <- jetstreamManager.Run(ctx)
	}()

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
	batchLatency, err := durationEnv(lookup, "WORKER_BATCH_LATENCY", defaultBatchLatency)
	if err != nil {
		return config{}, err
	}
	configRefetchInterval, err := durationEnv(lookup, "WORKER_CONFIG_REFETCH_INTERVAL", defaultConfigRefetchInterval)
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
	duplicateDetectionEnabled, err := boolEnv(lookup, "DUPLICATE_DETECTION_ENABLED", false)
	if err != nil {
		return config{}, err
	}
	duplicateDetectionInterval, err := durationEnv(lookup, "DUPLICATE_DETECTION_INTERVAL", defaultDuplicateDetectionInterval)
	if err != nil {
		return config{}, err
	}

	return config{
		DatabaseURL:                databaseURL,
		WorkerID:                   stringEnv(lookup, "WORKER_ID", defaultWorkerID()),
		PollInterval:               pollInterval,
		BatchLatency:               batchLatency,
		ConfigRefetchInterval:      configRefetchInterval,
		EncryptionKeyID:            encryptionKeyID,
		EncryptionKey:              encryptionKey,
		DuplicateDetectionEnabled:  duplicateDetectionEnabled,
		DuplicateDetectionInterval: duplicateDetectionInterval,
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

func boolEnv(lookup lookupFunc, key string, fallback bool) (bool, error) {
	value, ok := lookup(key)
	if !ok || value == "" {
		return fallback, nil
	}

	parsed, err := strconv.ParseBool(value)
	if err != nil {
		return false, fmt.Errorf("parse %s: %w", key, err)
	}

	return parsed, nil
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
