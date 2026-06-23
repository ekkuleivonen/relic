package storage

import (
	"errors"
	"testing"
)

func TestNewRejectsNilPool(t *testing.T) {
	store, err := New(nil)
	if !errors.Is(err, ErrNilPool) {
		t.Fatalf("New error = %v, want %v", err, ErrNilPool)
	}
	if store != nil {
		t.Fatal("New returned non-nil store")
	}
}
