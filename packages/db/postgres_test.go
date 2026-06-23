package db

import (
	"context"
	"os"
	"testing"
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
	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		t.Skip("DATABASE_URL is not set")
	}

	pool, err := Connect(context.Background(), databaseURL)
	if err != nil {
		t.Fatalf("Connect returned error: %v", err)
	}
	defer pool.Close()
}
