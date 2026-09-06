package tracecompletion

import (
	"context"
	"log/slog"

	"github.com/ekkuleivonen/relic/packages/storage"
)

type Ticker struct {
	store  *storage.Store
	logger *slog.Logger
}

type Options struct {
	Store  *storage.Store
	Logger *slog.Logger
}

func New(options Options) (*Ticker, error) {
	if options.Store == nil {
		return nil, errStoreRequired
	}

	logger := options.Logger
	if logger == nil {
		logger = slog.Default()
	}

	return &Ticker{
		store:  options.Store,
		logger: logger,
	}, nil
}

func (t *Ticker) Tick(ctx context.Context) (int, error) {
	awaiting, err := t.store.JobRuns().ListAwaitingTraceJobs(ctx, 100)
	if err != nil {
		return 0, err
	}
	if len(awaiting) == 0 {
		return 0, nil
	}

	seenTraces := map[string]struct{}{}
	traceOrder := []string{}
	for _, job := range awaiting {
		if _, ok := seenTraces[job.TraceID]; ok {
			continue
		}
		seenTraces[job.TraceID] = struct{}{}
		traceOrder = append(traceOrder, job.TraceID)
	}

	processed := 0
	for _, traceID := range traceOrder {
		summary, err := t.store.JobRuns().SummarizeTrace(ctx, traceID)
		if err != nil {
			return processed, err
		}

		for _, job := range awaiting {
			if job.TraceID != traceID {
				continue
			}

			count, err := t.processAwaitingJob(ctx, job, summary)
			if err != nil {
				return processed, err
			}
			processed += count
		}
	}

	return processed, nil
}

func (t *Ticker) processAwaitingJob(
	ctx context.Context,
	job storage.JobRun,
	summary storage.TraceSummary,
) (int, error) {
	current, err := t.store.JobRuns().GetJobRun(ctx, job.ID)
	if err != nil {
		return 0, err
	}
	if current.State != storage.JobRunStateRunning || !storage.PayloadBool(current.Result, "await_children") {
		return 0, nil
	}

	complete, err := t.store.JobRuns().DirectChildrenComplete(ctx, current.ID)
	if err != nil {
		return 0, err
	}
	if !complete {
		if storage.IsRootJob(current) {
			rollup := storage.TraceProgressRollup(summary)
			if _, err := t.store.JobRuns().UpdateJobRunProgress(ctx, storage.UpdateJobRunProgressParams{
				ID:       current.ID,
				Progress: rollup,
			}); err != nil {
				return 0, err
			}
		}
		return 1, nil
	}

	finalized, err := t.store.JobRuns().FinalizeAwaitingJob(ctx, current, summary)
	if err != nil {
		return 0, err
	}
	if finalized {
		t.logger.Info(
			"awaiting job finalized",
			"job_run_id", current.ID,
			"type", current.Type,
			"trace_id", current.TraceID,
		)
		return 1, nil
	}

	return 0, nil
}
