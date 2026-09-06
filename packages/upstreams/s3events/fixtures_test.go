package s3events

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/elei-io/pithosys/packages/upstreams/s3compat"
)

type notificationFixture struct {
	Upstream  s3compat.Upstream `json:"upstream"`
	Kind      string            `json:"kind"`
	Transport string            `json:"transport"`
	Source    string            `json:"source"`
	Body      json.RawMessage   `json:"body"`
}

func loadNotificationFixture(name string) (notificationFixture, error) {
	path := filepath.Join("testdata", "notifications", name)
	encoded, err := os.ReadFile(path)
	if err != nil {
		return notificationFixture{}, fmt.Errorf("read notification fixture %q: %w", name, err)
	}

	var fixture notificationFixture
	if err := json.Unmarshal(encoded, &fixture); err != nil {
		return notificationFixture{}, fmt.Errorf("decode notification fixture %q: %w", name, err)
	}

	return fixture, nil
}
