package storage

import (
	"testing"

	"github.com/ekkuleivonen/relic/packages/search"
)

func TestCatalogValueTypeRoundTrip(t *testing.T) {
	tests := []search.ValueType{
		search.TypeString,
		search.TypeInteger,
		search.TypeFloat,
		search.TypeBoolean,
		search.TypeTimestamp,
		search.TypeUnknown,
	}

	for _, typ := range tests {
		t.Run(string(typ), func(t *testing.T) {
			dbValue, err := catalogValueTypeToDB(typ)
			if err != nil {
				t.Fatalf("catalogValueTypeToDB returned error: %v", err)
			}

			got, err := catalogValueTypeFromDB(dbValue)
			if err != nil {
				t.Fatalf("catalogValueTypeFromDB returned error: %v", err)
			}
			if got != typ {
				t.Fatalf("round trip = %q, want %q", got, typ)
			}
		})
	}
}

func TestCatalogValueTypeToDBRejectsNull(t *testing.T) {
	if _, err := catalogValueTypeToDB(search.TypeNull); err == nil {
		t.Fatal("catalogValueTypeToDB returned nil error for null type")
	}
}

func TestWidenCatalogValueType(t *testing.T) {
	tests := []struct {
		existing search.ValueType
		incoming search.ValueType
		want     search.ValueType
		ok       bool
	}{
		{search.TypeInteger, search.TypeInteger, search.TypeInteger, true},
		{search.TypeInteger, search.TypeFloat, search.TypeFloat, true},
		{search.TypeFloat, search.TypeInteger, search.TypeFloat, true},
		{search.TypeString, search.TypeInteger, "", false},
	}

	for _, tt := range tests {
		t.Run(string(tt.existing)+"_"+string(tt.incoming), func(t *testing.T) {
			got, ok := widenCatalogValueType(tt.existing, tt.incoming)
			if ok != tt.ok {
				t.Fatalf("ok = %v, want %v", ok, tt.ok)
			}
			if got != tt.want {
				t.Fatalf("widened type = %q, want %q", got, tt.want)
			}
		})
	}
}
