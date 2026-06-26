package main

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	workerRunner "github.com/ekkuleivonen/relic/apps/worker/internal/runner"
	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/jobs"
	"github.com/ekkuleivonen/relic/packages/storage"
)

const defaultPollInterval = 2 * time.Second

type config struct {
	DatabaseURL  string
	WorkerID     string
	PollInterval time.Duration
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

	syncBucketHandler, err := jobs.NewSyncBucketStubHandler(store)
	if err != nil {
		return err
	}
	registry, err := jobs.NewRegistry(syncBucketHandler)
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

	slog.Info("worker started", "worker_id", cfg.WorkerID, "poll_interval", cfg.PollInterval)
	if err := jobRunner.Run(ctx); err != nil && !errors.Is(err, context.Canceled) {
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

	pollInterval, err := durationEnv(lookup, "WORKER_POLL_INTERVAL", defaultPollInterval)
	if err != nil {
		return config{}, err
	}

	return config{
		DatabaseURL:  databaseURL,
		WorkerID:     stringEnv(lookup, "WORKER_ID", defaultWorkerID()),
		PollInterval: pollInterval,
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
