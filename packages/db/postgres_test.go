package db

import (
	"context"
	"testing"

	"github.com/ekkuleivonen/relic/packages/testdb"
)

func TestConnectRejectsMissingDatabaseURL(t *testing.T) {
	pool, err := Connect(context.Background(), "")
	if err == nil {
		if pool != nil {
			pool.Close()
		}
		t.Fatal("Connect returned nil error")
	}
}

func TestConnectRejectsInvalidDatabaseURL(t *testing.T) {
	pool, err := Connect(context.Background(), "not a postgres url")
	if err == nil {
		if pool != nil {
			pool.Close()
		}
		t.Fatal("Connect returned nil error")
	}
}

func TestConnectWithDatabaseURL(t *testing.T) {
	ctx := context.Background()
	pool, err := Connect(ctx, testdb.URL(t, ctx))
	if err != nil {
		t.Fatalf("Connect returned error: %v", err)
	}
	defer pool.Close()
}
