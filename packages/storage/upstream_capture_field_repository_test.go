package storage

import (
	"context"
	"errors"
	"testing"

	"github.com/ekkuleivonen/relic/packages/search"
)

func TestSeedUpstreamCaptureFields(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	capture := store.UpstreamCaptureFields()
	if err := SeedUpstreamCaptureFields(ctx, capture); err != nil {
		t.Fatalf("SeedUpstreamCaptureFields returned error: %v", err)
	}

	fields, err := capture.List(ctx)
	if err != nil {
		t.Fatalf("List returned error: %v", err)
	}
	if len(fields) != len(PlatformUpstreamCaptureFields()) {
		t.Fatalf("field count = %d, want %d", len(fields), len(PlatformUpstreamCaptureFields()))
	}
}

func TestUpstreamCaptureFieldStoreCreateUser(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	capture := store.UpstreamCaptureFields()
	field, err := capture.CreateUser(ctx, CreateUpstreamCaptureFieldParams{
		AttributePath: "upstream.vendor.deployment_id",
		Enabled:       true,
		CaptureSource: CaptureSourceHead,
		ExtractorType: CaptureExtractorResponseHeader,
		ExtractorRef:  "X-Acme-Deployment-Id",
		ValueType:     search.TypeString,
	})
	if err != nil {
		t.Fatalf("CreateUser returned error: %v", err)
	}
	if field.Origin != CaptureFieldOriginUser {
		t.Fatalf("origin = %q, want user", field.Origin)
	}
	if field.ExtractorRef != "x-acme-deployment-id" {
		t.Fatalf("extractor_ref = %q, want normalized header", field.ExtractorRef)
	}
}

func TestUpstreamCaptureFieldStoreCreateUserRejectsSDKField(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	_, err := store.UpstreamCaptureFields().CreateUser(ctx, CreateUpstreamCaptureFieldParams{
		AttributePath: "upstream.header.content_type",
		Enabled:       true,
		CaptureSource: CaptureSourceHead,
		ExtractorType: CaptureExtractorSDKField,
		ExtractorRef:  "ContentType",
		ValueType:     search.TypeString,
	})
	if err == nil {
		t.Fatal("CreateUser returned nil error, want sdk_field rejection")
	}
}

func TestUpstreamCaptureFieldStoreUpdateRequiredGuard(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	capture := store.UpstreamCaptureFields()
	if err := SeedUpstreamCaptureFields(ctx, capture); err != nil {
		t.Fatalf("SeedUpstreamCaptureFields returned error: %v", err)
	}

	disabled := false
	_, err := capture.Update(ctx, "upstream.head.etag", UpdateUpstreamCaptureFieldParams{
		Enabled: &disabled,
	})
	if !errors.Is(err, ErrCaptureFieldRequired) {
		t.Fatalf("Update error = %v, want %v", err, ErrCaptureFieldRequired)
	}
}

func TestUpstreamCaptureFieldStoreDeleteUserOnly(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	capture := store.UpstreamCaptureFields()
	if err := SeedUpstreamCaptureFields(ctx, capture); err != nil {
		t.Fatalf("SeedUpstreamCaptureFields returned error: %v", err)
	}

	field, err := capture.CreateUser(ctx, CreateUpstreamCaptureFieldParams{
		AttributePath: "upstream.vendor.deployment_id",
		Enabled:       true,
		CaptureSource: CaptureSourceHead,
		ExtractorType: CaptureExtractorResponseHeader,
		ExtractorRef:  "x-acme-deployment-id",
		ValueType:     search.TypeString,
	})
	if err != nil {
		t.Fatalf("CreateUser returned error: %v", err)
	}

	if err := capture.DeleteUser(ctx, field.ID); err != nil {
		t.Fatalf("DeleteUser returned error: %v", err)
	}
	if err := capture.DeleteUser(ctx, "upstream.head.etag"); !errors.Is(err, ErrCaptureFieldPlatformOnly) {
		t.Fatalf("DeleteUser platform error = %v, want %v", err, ErrCaptureFieldPlatformOnly)
	}
}

func TestUpstreamCaptureFieldStoreListEnabled(t *testing.T) {
	ctx := context.Background()
	store, cleanup := testStore(t, ctx)
	defer cleanup()

	capture := store.UpstreamCaptureFields()
	if err := SeedUpstreamCaptureFields(ctx, capture); err != nil {
		t.Fatalf("SeedUpstreamCaptureFields returned error: %v", err)
	}

	disabled := false
	if _, err := capture.Update(ctx, "upstream.head.header.content_type", UpdateUpstreamCaptureFieldParams{
		Enabled: &disabled,
	}); err != nil {
		t.Fatalf("Update returned error: %v", err)
	}

	enabled, err := capture.ListEnabled(ctx)
	if err != nil {
		t.Fatalf("ListEnabled returned error: %v", err)
	}

	for _, field := range enabled {
		if field.ID == "upstream.head.header.content_type" {
			t.Fatal("disabled field present in ListEnabled")
		}
	}
}
