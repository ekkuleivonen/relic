package storage

import (
	"encoding/json"
	"testing"
)

func TestJSONBPath(t *testing.T) {
	path, err := NewJSONBPath("provider", "etag")
	if err != nil {
		t.Fatalf("NewJSONBPath returned error: %v", err)
	}

	if got, want := path.Dot(), "provider.etag"; got != want {
		t.Fatalf("Dot = %q, want %q", got, want)
	}

	parts := path.TextArray()
	parts[0] = "mutated"
	if got, want := path.Dot(), "provider.etag"; got != want {
		t.Fatalf("TextArray mutated path: got %q, want %q", got, want)
	}
}

func TestJSONBPathRejectsEmptySegments(t *testing.T) {
	if _, err := NewJSONBPath("provider", ""); err == nil {
		t.Fatal("NewJSONBPath returned nil error")
	}
}

func TestNewJSONBSetEncodesValue(t *testing.T) {
	path, err := NewJSONBPath("provider", "size")
	if err != nil {
		t.Fatalf("NewJSONBPath returned error: %v", err)
	}

	set, err := NewJSONBSet(path, 1048576)
	if err != nil {
		t.Fatalf("NewJSONBSet returned error: %v", err)
	}

	var got int
	if err := json.Unmarshal(set.Value, &got); err != nil {
		t.Fatalf("unmarshal value: %v", err)
	}
	if got != 1048576 {
		t.Fatalf("Value = %d, want 1048576", got)
	}
}
