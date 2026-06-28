package jetstreamconsumer

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/ekkuleivonen/relic/apps/worker/internal/settings"
	"github.com/ekkuleivonen/relic/packages/storage"
)

const defaultConfigRefetchInterval = 5 * time.Minute

type Manager struct {
	store    *storage.Store
	logger   *slog.Logger
	settings settings.Reader
	mu       sync.Mutex
	running  map[string]*managedConsumer
}

type ManagerOptions struct {
	Store    *storage.Store
	Logger   *slog.Logger
	Settings settings.Reader
}

type managedConsumer struct {
	cancel context.CancelFunc
	done   chan struct{}
	config storage.BucketJetStreamConfig
}

func NewManager(options ManagerOptions) (*Manager, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create jetstream manager: storage store is required")
	}
	if options.Settings == nil {
		return nil, fmt.Errorf("create jetstream manager: settings reader is required")
	}

	logger := options.Logger
	if logger == nil {
		logger = slog.Default()
	}

	return &Manager{
		store:    options.Store,
		logger:   logger,
		settings: options.Settings,
		running:  make(map[string]*managedConsumer),
	}, nil
}

func (m *Manager) Run(ctx context.Context) error {
	if err := m.sync(ctx); err != nil {
		return err
	}

	for {
		interval := m.settings.Duration(storage.SettingWorkerConfigRefetchInterval)
		if interval <= 0 {
			interval = defaultConfigRefetchInterval
		}

		select {
		case <-ctx.Done():
			m.stopAll()
			return ctx.Err()
		case <-time.After(interval):
			if err := m.sync(ctx); err != nil {
				return err
			}
		}
	}
}

func (m *Manager) sync(ctx context.Context) error {
	desired, parseErrors, err := m.loadDesiredConfigs(ctx)
	if err != nil {
		return err
	}
	for bucketID, err := range parseErrors {
		m.logger.Error(
			"invalid bucket jetstream config",
			"bucket_id", bucketID,
			"error", err,
		)
	}

	started, stopped, unchanged := m.reconcile(ctx, desired)

	if started > 0 || stopped > 0 {
		m.logger.Info(
			"jetstream consumer sync complete",
			"started", started,
			"stopped", stopped,
			"unchanged", unchanged,
			"desired", len(desired),
			"running", len(m.running),
		)
	} else {
		m.logger.Debug(
			"jetstream consumer sync complete",
			"unchanged", unchanged,
			"desired", len(desired),
			"running", len(m.running),
		)
	}

	return nil
}

func (m *Manager) loadDesiredConfigs(ctx context.Context) (map[string]storage.BucketJetStreamConfig, map[string]error, error) {
	desired := make(map[string]storage.BucketJetStreamConfig)
	parseErrors := make(map[string]error)

	offset := 0
	const pageSize = 500

	for {
		buckets, err := m.store.Buckets().ListBuckets(ctx, storage.ListBucketsParams{
			Limit:  pageSize,
			Offset: offset,
		})
		if err != nil {
			return nil, nil, fmt.Errorf("list buckets for jetstream sync: %w", err)
		}

		for _, bucket := range buckets {
			cfg, enabled, err := storage.ParseBucketJetStreamConfig(bucket.ID, bucket.UpstreamConfig)
			if err != nil {
				parseErrors[bucket.ID] = err
				continue
			}
			if enabled {
				desired[bucket.ID] = cfg
			}
		}

		if len(buckets) < pageSize {
			break
		}
		offset += pageSize
	}

	return desired, parseErrors, nil
}

func (m *Manager) reconcile(ctx context.Context, desired map[string]storage.BucketJetStreamConfig) (started, stopped, unchanged int) {
	m.mu.Lock()

	waiting := []*managedConsumer{}
	for bucketID, managed := range m.running {
		cfg, ok := desired[bucketID]
		if !ok || !cfg.Equal(managed.config) {
			managed.cancel()
			delete(m.running, bucketID)
			waiting = append(waiting, managed)
			stopped++
		}
	}
	m.mu.Unlock()

	for _, managed := range waiting {
		<-managed.done
	}

	m.mu.Lock()
	defer m.mu.Unlock()

	for bucketID, cfg := range desired {
		managed, ok := m.running[bucketID]
		if ok && cfg.Equal(managed.config) {
			unchanged++
			continue
		}

		if m.startLocked(ctx, bucketID, cfg) {
			started++
		}
	}

	return started, stopped, unchanged
}

func (m *Manager) startLocked(ctx context.Context, bucketID string, cfg storage.BucketJetStreamConfig) bool {
	consumer, err := NewConsumer(ConsumerOptions{
		Store:    m.store,
		Logger:   m.logger,
		BucketID: bucketID,
		URL:      cfg.URL,
		Stream:   cfg.Stream,
		Subject:  cfg.Subject,
		Consumer: cfg.Consumer,
	})
	if err != nil {
		m.logger.Error(
			"create jetstream consumer failed",
			"bucket_id", bucketID,
			"error", err,
		)
		return false
	}

	childCtx, cancel := context.WithCancel(ctx)
	done := make(chan struct{})
	managed := &managedConsumer{
		cancel: cancel,
		done:   done,
		config: cfg,
	}
	m.running[bucketID] = managed

	go func() {
		defer close(done)
		err := consumer.Run(childCtx)
		if err != nil && !errors.Is(err, context.Canceled) {
			m.logger.Error(
				"jetstream consumer stopped with error",
				"bucket_id", bucketID,
				"error", err,
			)
		}
		m.removeRunning(bucketID, managed)
	}()

	return true
}

func (m *Manager) removeRunning(bucketID string, managed *managedConsumer) {
	m.mu.Lock()
	defer m.mu.Unlock()

	current, ok := m.running[bucketID]
	if !ok || current != managed {
		return
	}

	delete(m.running, bucketID)
}

func (m *Manager) stopAll() {
	m.mu.Lock()
	waiting := make([]*managedConsumer, 0, len(m.running))
	for bucketID, managed := range m.running {
		managed.cancel()
		waiting = append(waiting, managed)
		delete(m.running, bucketID)
	}
	m.mu.Unlock()

	for _, managed := range waiting {
		<-managed.done
	}
}

func diffJetStreamConsumers(
	desired map[string]storage.BucketJetStreamConfig,
	running map[string]storage.BucketJetStreamConfig,
) (toStart, toStop, unchanged []string) {
	for bucketID, cfg := range desired {
		current, ok := running[bucketID]
		if ok && cfg.Equal(current) {
			unchanged = append(unchanged, bucketID)
			continue
		}
		toStart = append(toStart, bucketID)
	}

	for bucketID := range running {
		cfg, ok := desired[bucketID]
		if !ok {
			toStop = append(toStop, bucketID)
			continue
		}
		if !cfg.Equal(running[bucketID]) {
			toStop = append(toStop, bucketID)
		}
	}

	return toStart, toStop, unchanged
}
