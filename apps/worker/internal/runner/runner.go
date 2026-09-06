package runner

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/elei-io/pithosys/apps/worker/internal/jobs"
	"github.com/elei-io/pithosys/apps/worker/internal/settings"
	"github.com/elei-io/pithosys/apps/worker/internal/tracecompletion"
	"github.com/elei-io/pithosys/packages/storage"
)

type Runner struct {
	store           *storage.Store
	registry        *jobs.Registry
	traceCompletion *tracecompletion.Ticker
	workerID        string
	settings        settings.Reader
	logger          *slog.Logger
}

type Options struct {
	Store    *storage.Store
	Registry *jobs.Registry
	WorkerID string
	Settings settings.Reader
	Logger   *slog.Logger
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
	if options.Settings == nil {
		return nil, fmt.Errorf("create job runner: settings reader is required")
	}
	if options.Logger == nil {
		options.Logger = slog.Default()
	}

	traceCompletion, err := tracecompletion.New(tracecompletion.Options{
		Store:  options.Store,
		Logger: options.Logger,
	})
	if err != nil {
		return nil, err
	}

	return &Runner{
		store:           options.Store,
		registry:        options.Registry,
		traceCompletion: traceCompletion,
		workerID:        options.WorkerID,
		settings:        options.Settings,
		logger:          options.Logger,
	}, nil
}

func (r *Runner) Run(ctx context.Context) error {
	for {
		claimed, err := r.RunOnce(ctx)
		if err != nil {
			return err
		}
		if claimed {
			continue
		}

		if _, err := r.store.JobRuns().ReclaimStaleLockedJobs(ctx, storage.ReclaimStaleLockedJobsParams{
			StaleAfter: r.settings.Duration(storage.SettingWorkerJobStaleTimeout),
		}); err != nil {
			return err
		}

		if _, err := r.traceCompletion.Tick(ctx); err != nil {
			return err
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(r.settings.Duration(storage.SettingWorkerRunnerPollInterval)):
		}
	}
}

func (r *Runner) RunOnce(ctx context.Context) (bool, error) {
	run, err := r.store.JobRuns().ClaimJobRun(ctx, storage.ClaimJobRunParams{
		WorkerID: r.workerID,
		Types:    r.registry.Types(),
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

	if jobs.AwaitsChildren(result) {
		progress := jobs.FanOutProgress(result)
		if _, err := r.store.JobRuns().AwaitJobRunChildren(ctx, storage.AwaitJobRunChildrenParams{
			ID:       run.ID,
			Result:   result,
			Progress: progress,
		}); err != nil {
			return true, err
		}
		r.logger.Info("job awaiting child completion", "job_run_id", run.ID, "type", run.Type, "trace_id", run.TraceID)
		return true, nil
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
		retryDelay := r.settings.Duration(storage.SettingWorkerRunnerRetryDelay)
		availableAt := time.Now().Add(retryDelay)
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
