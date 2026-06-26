package search

import "testing"

func TestFieldSQLColumnObjects(t *testing.T) {
	got, err := FieldSQLColumn(TargetObjects, "key")
	if err != nil {
		t.Fatalf("FieldSQLColumn returned error: %v", err)
	}
	if got != "objects.key" {
		t.Fatalf("column = %q, want objects.key", got)
	}
}

func TestFieldSQLColumnRejectsUnknownField(t *testing.T) {
	_, err := FieldSQLColumn(TargetObjects, "version_id")
	if err == nil {
		t.Fatal("FieldSQLColumn returned nil error")
	}
}
