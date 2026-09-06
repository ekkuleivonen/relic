package supervisor

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/elei-io/pithosys/apps/worker/internal/jetstreamconsumer"
	"github.com/elei-io/pithosys/apps/worker/internal/jobs"
	"github.com/elei-io/pithosys/apps/worker/internal/runner"
	scanscheduler "github.com/elei-io/pithosys/apps/worker/internal/scheduler"
	"github.com/elei-io/pithosys/apps/worker/internal/settings"
	"github.com/elei-io/pithosys/apps/worker/internal/upstreamprocessor"
	"github.com/elei-io/pithosys/packages/storage"
)

const (
	workerScanScheduler          = "scan_scheduler"
	workerDuplicateDetection     = "duplicate_detection"
)

type Options struct {
	Store    *storage.Store
	Registry *jobs.Registry
	WorkerID string
	Logger   *slog.Logger
}

type Supervisor struct {
	store    *storage.Store
	registry *jobs.Registry
	workerID string
	logger   *slog.Logger
	cache    *settings.Cache

	mu         sync.Mutex
	supervised map[string]*managedWorker
}

type managedWorker struct {
	cancel context.CancelFunc
	done   chan struct{}
}

func New(options Options) (*Supervisor, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create supervisor: storage store is required")
	}
	if options.Registry == nil {
		return nil, fmt.Errorf("create supervisor: handler registry is required")
	}
	if options.WorkerID == "" {
		return nil, fmt.Errorf("create supervisor: worker ID is required")
	}

	logger := options.Logger
	if logger == nil {
		logger = slog.Default()
	}

	return &Supervisor{
		store:      options.Store,
		registry:   options.Registry,
		workerID:   options.WorkerID,
		logger:     logger,
		cache:      settings.NewCache(),
		supervised: make(map[string]*managedWorker),
	}, nil
}

func (s *Supervisor) Run(ctx context.Context) error {
	if err := s.cache.Refresh(ctx, s.store.Settings()); err != nil {
		return fmt.Errorf("refresh settings: %w", err)
	}

	jobRunner, err := runner.New(runner.Options{
		Store:    s.store,
		Registry: s.registry,
		WorkerID: s.workerID,
		Settings: s.cache,
		Logger:   s.logger,
	})
	if err != nil {
		return err
	}

	upstreamProcessor, err := upstreamprocessor.NewProcessor(upstreamprocessor.ProcessorOptions{
		Store:    s.store,
		Logger:   s.logger,
		Settings: s.cache,
	})
	if err != nil {
		return err
	}

	jetstreamManager, err := jetstreamconsumer.NewManager(jetstreamconsumer.ManagerOptions{
		Store:    s.store,
		Logger:   s.logger,
		Settings: s.cache,
	})
	if err != nil {
		return err
	}

	errCh := make(chan error, 4)

	go func() {
		s.logger.Info("job runner started", "worker_id", s.workerID)
		errCh <- jobRunner.Run(ctx)
	}()

	go func() {
		s.logger.Info("upstream event processor started")
		errCh <- upstreamProcessor.Run(ctx)
	}()

	go func() {
		s.logger.Info("jetstream consumer manager started")
		errCh <- jetstreamManager.Run(ctx)
	}()

	go func() {
		errCh <- s.supervisorLoop(ctx)
	}()

	var runErr error
	for i := 0; i < 4; i++ {
		if err := <-errCh; err != nil && !errors.Is(err, context.Canceled) {
			runErr = err
		}
	}

	if runErr != nil {
		return runErr
	}

	return nil
}

func (s *Supervisor) supervisorLoop(ctx context.Context) error {
	s.reconcile(ctx)

	for {
		select {
		case <-ctx.Done():
			s.stopSupervised()
			return ctx.Err()
		case <-timeAfterRefetch(s.cache):
			if err := s.cache.Refresh(ctx, s.store.Settings()); err != nil {
				return fmt.Errorf("refresh settings: %w", err)
			}
			s.reconcile(ctx)
		}
	}
}

func (s *Supervisor) reconcile(ctx context.Context) {
	desired := map[string]bool{
		workerScanScheduler:      s.cache.Bool(storage.SettingScanBucketEnabled),
		workerDuplicateDetection: s.cache.Bool(storage.SettingDuplicateDetectionEnabled),
	}

	started, stopped := s.reconcileWorkers(ctx, desired)
	if started > 0 || stopped > 0 {
		s.logger.Info(
			"supervisor reconcile complete",
			"started", started,
			"stopped", stopped,
			"scan_bucket_enabled", desired[workerScanScheduler],
			"duplicate_detection_enabled", desired[workerDuplicateDetection],
		)
	}
}

func (s *Supervisor) reconcileWorkers(ctx context.Context, desired map[string]bool) (started, stopped int) {
	s.mu.Lock()

	waiting := []*managedWorker{}
	for name, managed := range s.supervised {
		if !desired[name] {
			managed.cancel()
			delete(s.supervised, name)
			waiting = append(waiting, managed)
			stopped++
		}
	}
	s.mu.Unlock()

	for _, managed := range waiting {
		<-managed.done
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	for name, enabled := range desired {
		if !enabled {
			continue
		}
		if _, ok := s.supervised[name]; ok {
			continue
		}
		if s.startLocked(ctx, name) {
			started++
		}
	}

	return started, stopped
}

func (s *Supervisor) startLocked(ctx context.Context, name string) bool {
	runner, err := s.newSupervisedWorker(name)
	if err != nil {
		s.logger.Error("create supervised worker failed", "worker", name, "error", err)
		return false
	}

	childCtx, cancel := context.WithCancel(ctx)
	done := make(chan struct{})
	managed := &managedWorker{
		cancel: cancel,
		done:   done,
	}
	s.supervised[name] = managed

	go func() {
		defer close(done)
		err := runner.Run(childCtx)
		if err != nil && !errors.Is(err, context.Canceled) {
			s.logger.Error("supervised worker stopped with error", "worker", name, "error", err)
		}
		s.removeSupervised(name, managed)
	}()

	s.logger.Info("supervised worker started", "worker", name)
	return true
}

func (s *Supervisor) newSupervisedWorker(name string) (interface {
	Run(context.Context) error
}, error) {
	switch name {
	case workerScanScheduler:
		return scanscheduler.NewScanScheduler(scanscheduler.ScanSchedulerOptions{
			Store:    s.store,
			Logger:   s.logger,
			Settings: s.cache,
		})
	case workerDuplicateDetection:
		return scanscheduler.NewDuplicateDetectionScheduler(scanscheduler.DuplicateDetectionSchedulerOptions{
			Store:    s.store,
			Logger:   s.logger,
			Settings: s.cache,
		})
	default:
		return nil, fmt.Errorf("unknown supervised worker %q", name)
	}
}

func (s *Supervisor) removeSupervised(name string, managed *managedWorker) {
	s.mu.Lock()
	defer s.mu.Unlock()

	current, ok := s.supervised[name]
	if !ok || current != managed {
		return
	}

	delete(s.supervised, name)
}

func (s *Supervisor) stopSupervised() {
	s.mu.Lock()
	waiting := make([]*managedWorker, 0, len(s.supervised))
	for name, managed := range s.supervised {
		managed.cancel()
		waiting = append(waiting, managed)
		delete(s.supervised, name)
	}
	s.mu.Unlock()

	for _, managed := range waiting {
		<-managed.done
	}
}

func timeAfterRefetch(cache *settings.Cache) <-chan time.Time {
	return time.After(cache.RefetchInterval())
}
