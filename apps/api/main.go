package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/ekkuleivonen/relic/apps/api/internal/config"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/packages/auth"
	"github.com/ekkuleivonen/relic/packages/db"
	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
)

const shutdownTimeout = 10 * time.Second

func main() {
	if err := run(); err != nil {
		slog.Error("api exited", "error", err)
		os.Exit(1)
	}
}

func run() error {
	cfg, err := config.Load()
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

	authService, err := auth.NewService(cfg.AuthServiceConfig(), store)
	if err != nil {
		return err
	}
	if err := authService.EnsureBootstrapAdmin(ctx); err != nil {
		return err
	}
	slog.Info("bootstrap admin ensured")

	srv := httpserver.New(deps.Dependencies{
		Config:  cfg,
		Secrets: secretManager,
		Storage: store,
		Auth:    authService,
	})
	errCh := make(chan error, 1)

	go func() {
		slog.Info("api listening", "addr", srv.Addr)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			errCh <- err
		}
		close(errCh)
	}()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	select {
	case <-ctx.Done():
		slog.Info("api shutting down")
	case err := <-errCh:
		return err
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()

	if err := srv.Shutdown(shutdownCtx); err != nil {
		return err
	}

	if err := <-errCh; err != nil {
		return err
	}

	slog.Info("api stopped")
	return nil
}
