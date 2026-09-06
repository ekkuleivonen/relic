package jetstreamconsumer

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"github.com/elei-io/pithosys/packages/storage"
	upstreameventsingest "github.com/elei-io/pithosys/packages/upstreamevents"
	"github.com/nats-io/nats.go"
)

const (
	defaultAckWait    = 30 * time.Second
	defaultFetchBatch = 10
	defaultFetchWait  = time.Second
)

type Consumer struct {
	store    *storage.Store
	logger   *slog.Logger
	bucketID string
	url      string
	stream   string
	subject  string
	consumer string
}

type ConsumerOptions struct {
	Store    *storage.Store
	Logger   *slog.Logger
	BucketID string
	URL      string
	Stream   string
	Subject  string
	Consumer string
}

func NewConsumer(options ConsumerOptions) (*Consumer, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create jetstream consumer: storage store is required")
	}
	if strings.TrimSpace(options.BucketID) == "" {
		return nil, fmt.Errorf("create jetstream consumer: bucket id is required")
	}
	if strings.TrimSpace(options.URL) == "" {
		return nil, fmt.Errorf("create jetstream consumer: nats url is required")
	}
	if strings.TrimSpace(options.Stream) == "" {
		return nil, fmt.Errorf("create jetstream consumer: stream is required")
	}
	if strings.TrimSpace(options.Subject) == "" {
		return nil, fmt.Errorf("create jetstream consumer: subject is required")
	}

	logger := options.Logger
	if logger == nil {
		logger = slog.Default()
	}
	consumer := strings.TrimSpace(options.Consumer)
	if consumer == "" {
		consumer = storage.DefaultJetStreamConsumerName(options.BucketID)
	}

	return &Consumer{
		store:    options.Store,
		logger:   logger,
		bucketID: strings.TrimSpace(options.BucketID),
		url:      strings.TrimSpace(options.URL),
		stream:   strings.TrimSpace(options.Stream),
		subject:  strings.TrimSpace(options.Subject),
		consumer: consumer,
	}, nil
}

func ensureConsumer(js nats.JetStreamContext, stream, consumer, subject string) error {
	cfg := &nats.ConsumerConfig{
		Durable:       consumer,
		FilterSubject: subject,
		AckPolicy:     nats.AckExplicitPolicy,
		AckWait:       defaultAckWait,
		MaxDeliver:    5,
		DeliverPolicy: nats.DeliverAllPolicy,
	}

	_, err := js.AddConsumer(stream, cfg)
	if err == nil {
		return nil
	}
	if !errors.Is(err, nats.ErrConsumerNameAlreadyInUse) {
		return err
	}

	_, err = js.UpdateConsumer(stream, cfg)
	return err
}

func (c *Consumer) Run(ctx context.Context) error {
	nc, err := nats.Connect(c.url)
	if err != nil {
		return fmt.Errorf("connect nats: %w", err)
	}
	defer nc.Close()

	js, err := nc.JetStream()
	if err != nil {
		return fmt.Errorf("create jetstream context: %w", err)
	}

	if err := ensureConsumer(js, c.stream, c.consumer, c.subject); err != nil {
		return fmt.Errorf("ensure jetstream consumer: %w", err)
	}

	sub, err := js.PullSubscribe(c.subject, c.consumer, nats.Bind(c.stream, c.consumer))
	if err != nil {
		return fmt.Errorf("pull subscribe jetstream consumer: %w", err)
	}
	defer sub.Unsubscribe()

	c.logger.Info(
		"jetstream upstream consumer started",
		"bucket_id", c.bucketID,
		"url", c.url,
		"stream", c.stream,
		"subject", c.subject,
		"consumer", c.consumer,
	)

	for {
		fetchCtx, cancel := context.WithTimeout(ctx, defaultFetchWait)
		msgs, err := sub.Fetch(defaultFetchBatch, nats.Context(fetchCtx))
		cancel()
		if err != nil {
			if errors.Is(err, context.DeadlineExceeded) || errors.Is(err, nats.ErrTimeout) {
				continue
			}
			if errors.Is(err, context.Canceled) || ctx.Err() != nil {
				return ctx.Err()
			}
			return fmt.Errorf("fetch jetstream messages: %w", err)
		}

		for _, msg := range msgs {
			c.handleMessage(msg)
		}
	}
}

func (c *Consumer) handleMessage(msg *nats.Msg) {
	if msg == nil {
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()

	bucketID := c.bucketID
	result, err := upstreameventsingest.IngestS3Notification(
		ctx,
		c.store.UpstreamEvents(),
		msg.Data,
		bucketID,
	)
	if err != nil {
		c.logger.Error(
			"jetstream message ingest failed",
			"bucket_id", c.bucketID,
			"subject", msg.Subject,
			"error", err,
		)
		if nakErr := msg.Nak(); nakErr != nil {
			c.logger.Error("jetstream message nak failed", "error", nakErr)
		}
		return
	}

	if err := msg.Ack(); err != nil {
		c.logger.Error("jetstream message ack failed", "error", err)
		return
	}

	switch {
	case result.Accepted > 0 || result.Duplicate > 0:
		c.logger.Info(
			"jetstream message ingested",
			"bucket_id", c.bucketID,
			"subject", msg.Subject,
			"accepted", result.Accepted,
			"duplicate", result.Duplicate,
			"ignored", result.Ignored,
		)
	case result.Ignored > 0:
		c.logger.Warn(
			"jetstream message contained no actionable records",
			"bucket_id", c.bucketID,
			"subject", msg.Subject,
			"ignored", result.Ignored,
		)
	default:
		c.logger.Debug(
			"jetstream message acked with no records",
			"bucket_id", c.bucketID,
			"subject", msg.Subject,
		)
	}
}
