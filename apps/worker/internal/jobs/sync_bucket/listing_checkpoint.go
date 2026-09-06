package sync_bucket

import (
	"time"

	"github.com/elei-io/pithosys/apps/worker/internal/jobs"
	"github.com/elei-io/pithosys/packages/storage"
)

type listingCheckpoint struct {
	ContinuationToken string
	Marker            string
	ObjectsListed     int64
	ListingComplete   bool
	LastPageAt        string
}

func listingCheckpointFromProgress(progress storage.JobRunPayload) listingCheckpoint {
	checkpoint := listingCheckpoint{}
	if progress == nil {
		return checkpoint
	}

	if listed := storage.PayloadInt64(progress, "objects_listed"); listed > 0 {
		checkpoint.ObjectsListed = listed
	}
	if complete, ok := progress["listing_complete"].(bool); ok {
		checkpoint.ListingComplete = complete
	}
	if lastPageAt, ok := progress["last_page_at"].(string); ok {
		checkpoint.LastPageAt = lastPageAt
	}

	raw, ok := progress["listing_checkpoint"].(map[string]any)
	if !ok || raw == nil {
		return checkpoint
	}
	if token, ok := raw["continuation_token"].(string); ok {
		checkpoint.ContinuationToken = token
	}
	if marker, ok := raw["marker"].(string); ok {
		checkpoint.Marker = marker
	}
	if listed := storage.PayloadInt64(raw, "objects_listed"); listed > 0 {
		checkpoint.ObjectsListed = listed
	}
	if complete, ok := raw["listing_complete"].(bool); ok {
		checkpoint.ListingComplete = complete
	}

	return checkpoint
}

func (checkpoint listingCheckpoint) toListStart() jobs.ListCheckpoint {
	return jobs.ListCheckpoint{
		ContinuationToken: checkpoint.ContinuationToken,
		Marker:            checkpoint.Marker,
		ObjectsListed:     checkpoint.ObjectsListed,
	}
}

func listingCheckpointPayload(checkpoint jobs.ListCheckpoint, listingComplete bool) map[string]any {
	return map[string]any{
		"continuation_token": checkpoint.ContinuationToken,
		"marker":             checkpoint.Marker,
		"objects_listed":     checkpoint.ObjectsListed,
		"listing_complete":   listingComplete,
	}
}

func listingProgressFields(checkpoint jobs.ListCheckpoint, listingComplete bool, planned syncPlanCounts) storage.JobRunPayload {
	payload := storage.JobRunPayload{
		"phase":               "listing",
		"objects_listed":      checkpoint.ObjectsListed,
		"listing_complete":    listingComplete,
		"listing_checkpoint":  listingCheckpointPayload(checkpoint, listingComplete),
		"last_page_at":        time.Now().UTC().Format(time.RFC3339),
		"import_objects_count":  planned.Import,
		"refresh_objects_count": planned.Refresh,
		"remove_objects_count":  planned.Remove,
		"objects_planned": map[string]any{
			"import":  planned.Import,
			"refresh": planned.Refresh,
			"remove":  planned.Remove,
		},
	}

	return payload
}

func planningProgressFields(objectsListed int64, planned syncPlanCounts) storage.JobRunPayload {
	return storage.JobRunPayload{
		"phase":                 "planning",
		"objects_listed":        objectsListed,
		"listing_complete":      true,
		"import_objects_count":  planned.Import,
		"refresh_objects_count": planned.Refresh,
		"remove_objects_count":  planned.Remove,
		"objects_planned": map[string]any{
			"import":  planned.Import,
			"refresh": planned.Refresh,
			"remove":  planned.Remove,
		},
	}
}

type syncPlanCounts struct {
	Import  int
	Refresh int
	Remove  int
}

func (counts syncPlanCounts) add(importCount, refreshCount, removeCount int) syncPlanCounts {
	return syncPlanCounts{
		Import:  counts.Import + importCount,
		Refresh: counts.Refresh + refreshCount,
		Remove:  counts.Remove + removeCount,
	}
}
