package runner

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/ekkuleivonen/relic/apps/worker/internal/jobs"
	"github.com/ekkuleivonen/relic/packages/storage"
)

const (
	defaultPollInterval = 2 * time.Second
	defaultRetryDelay   = 30 * time.Second
)

type Runner struct {
	store        *storage.Store
	registry     *jobs.Registry
	workerID     string
	pollInterval time.Duration
	retryDelay   time.Duration
	logger       *slog.Logger
}

type Options struct {
	Store        *storage.Store
	Registry     *jobs.Registry
	WorkerID     string
	PollInterval time.Duration
	RetryDelay   time.Duration
	Logger       *slog.Logger
}

func New(options Options) (*Runner, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create job runner: storage store is required")
	}
	if options.Registry == nil {
		return nil, fmt.Errorf("create job runner: handler registry is required")
	}
	if options.WorkerID == "" {
		return nil, fmt.Errorf("create job runner: worker ID is required")
	}
	if options.PollInterval <= 0 {
		options.PollInterval = defaultPollInterval
	}
	if options.RetryDelay <= 0 {
		options.RetryDelay = defaultRetryDelay
	}
	if options.Logger == nil {
		options.Logger = slog.Default()
	}

	return &Runner{
		store:        options.Store,
		registry:     options.Registry,
		workerID:     options.WorkerID,
		pollInterval: options.PollInterval,
		retryDelay:   options.RetryDelay,
		logger:       options.Logger,
	}, nil
}

func (r *Runner) Run(ctx context.Context) error {
	ticker := time.NewTicker(r.pollInterval)
	defer ticker.Stop()

	for {
		claimed, err := r.RunOnce(ctx)
		if err != nil {
			return err
		}
		if claimed {
			continue
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (r *Runner) RunOnce(ctx context.Context) (bool, error) {
	run, err := r.store.JobRuns().ClaimJobRun(ctx, storage.ClaimJobRunParams{
		WorkerID: r.workerID,
	})
	if errors.Is(err, storage.ErrNotFound) {
		return false, nil
	}
	if err != nil {
		return false, err
	}

	r.logger.Info("job claimed", "job_run_id", run.ID, "type", run.Type)
	handler, ok := r.registry.Get(run.Type)
	if !ok {
		message := fmt.Sprintf("no handler registered for job type %q", run.Type)
		if _, err := r.store.JobRuns().FailJobRun(ctx, storage.FailJobRunParams{
			ID:           run.ID,
			ErrorMessage: message,
		}); err != nil {
			return true, err
		}
		r.logger.Error("job failed", "job_run_id", run.ID, "type", run.Type, "error", message)
		return true, nil
	}

	result, err := handler.Handle(ctx, run)
	if err != nil {
		return true, r.handleFailure(ctx, run, err)
	}

	if _, err := r.store.JobRuns().SucceedJobRun(ctx, storage.SucceedJobRunParams{
		ID:     run.ID,
		Result: result,
	}); err != nil {
		return true, err
	}
	r.logger.Info("job succeeded", "job_run_id", run.ID, "type", run.Type)

	return true, nil
}

func (r *Runner) handleFailure(ctx context.Context, run storage.JobRun, cause error) error {
	message := cause.Error()
	if run.Attempt < run.MaxAttempts {
		availableAt := time.Now().Add(r.retryDelay)
		if _, err := r.store.JobRuns().RetryJobRun(ctx, storage.RetryJobRunParams{
			ID:           run.ID,
			ErrorMessage: message,
			AvailableAt:  &availableAt,
		}); err != nil {
			return err
		}
		r.logger.Warn("job scheduled for retry", "job_run_id", run.ID, "type", run.Type, "error", message)
		return nil
	}

	if _, err := r.store.JobRuns().FailJobRun(ctx, storage.FailJobRunParams{
		ID:           run.ID,
		ErrorMessage: message,
	}); err != nil {
		return err
	}
	r.logger.Error("job failed", "job_run_id", run.ID, "type", run.Type, "error", message)

	return nil
}
