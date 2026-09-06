package s3events

import (
	"time"

	"github.com/elei-io/pithosys/packages/upstreams/s3compat"
)

type EventAction string

const (
	EventActionImport EventAction = "import"
	EventActionRemove EventAction = "remove"
	EventActionIgnore EventAction = "ignore"
)

type NormalizedEvent struct {
	Upstream     s3compat.Upstream
	Action       EventAction
	EventName    string
	EventSource  string
	BucketName   string
	BucketARN    string
	Region       string
	DeploymentID string
	Key          string
	ETag         string
	Size         int64
	EventTime    time.Time
	EventID      string
	VersionID    string
}
