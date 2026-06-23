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
	"github.com/ekkuleivonen/relic/packages/db"
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

	database, err := db.Connect(context.Background(), cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer database.Close()
	slog.Info("database connected")

	srv := httpserver.New(deps.Dependencies{
		Config: cfg,
		DB:     database,
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
