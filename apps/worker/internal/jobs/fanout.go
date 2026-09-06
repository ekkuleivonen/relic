package jobs

import "github.com/ekkuleivonen/relic/packages/storage"

const (
	ResultKeyChildJobIDs    = "child_job_ids"
	ResultKeyAwaitChildren  = "await_children"
)

func FanOutResult(childJobIDs map[string][]string, fields storage.JobRunPayload) storage.JobRunPayload {
	result := storage.JobRunPayload{}
	for key, value := range fields {
		result[key] = value
	}

	if len(childJobIDs) > 0 {
		encoded := make(map[string]any, len(childJobIDs))
		total := 0
		for jobType, ids := range childJobIDs {
			if len(ids) == 0 {
				continue
			}
			encoded[jobType] = ids
			total += len(ids)
		}
		if total > 0 {
			result[ResultKeyChildJobIDs] = encoded
			result[ResultKeyAwaitChildren] = true
		}
	}

	return result
}

func FanOutProgress(result storage.JobRunPayload) storage.JobRunPayload {
	progress := storage.JobRunPayload{
		"phase": awaitingPhase(result),
	}

	if count, ok := result["objects_seen"]; ok {
		progress["objects_listed"] = count
	}
	if count, ok := result["objects_listed"]; ok && progress["objects_listed"] == nil {
		progress["objects_listed"] = count
	}

	importCount, _ := result["import_objects_count"]
	refreshCount, _ := result["refresh_objects_count"]
	removeCount, _ := result["remove_objects_count"]
	if importCount != nil || refreshCount != nil || removeCount != nil {
		progress["import_objects_count"] = importCount
		progress["refresh_objects_count"] = refreshCount
		progress["remove_objects_count"] = removeCount
		progress["objects_planned"] = map[string]any{
			"import":  importCount,
			"refresh": refreshCount,
			"remove":  removeCount,
		}
	}

	batches := map[string]any{}
	if total := childTypeCount(result, "import_objects"); total > 0 {
		batches["import"] = map[string]any{"total": total}
	}
	if total := childTypeCount(result, "refresh_objects"); total > 0 {
		batches["refresh"] = map[string]any{"total": total}
	}
	if total := childTypeCount(result, "remove_objects"); total > 0 {
		batches["remove"] = map[string]any{"total": total}
	}
	if total := childTypeCount(result, "sync_bucket"); total > 0 {
		batches["sync_bucket"] = map[string]any{"total": total}
	}
	if len(batches) > 0 {
		progress["batches"] = batches
	}

	return progress
}

func awaitingPhase(result storage.JobRunPayload) string {
	if childTypeCount(result, "sync_bucket") > 0 {
		return "awaiting_sync"
	}

	return "applying"
}

func AwaitsChildren(result storage.JobRunPayload) bool {
	if result == nil {
		return false
	}
	if value, ok := result[ResultKeyAwaitChildren]; ok {
		switch typed := value.(type) {
		case bool:
			return typed
		}
	}

	return childJobCount(result) > 0
}

func childTypeCount(result storage.JobRunPayload, jobType string) int {
	raw, ok := result[ResultKeyChildJobIDs]
	if !ok || raw == nil {
		return 0
	}

	switch typed := raw.(type) {
	case map[string][]string:
		return len(typed[jobType])
	case map[string]any:
		value, ok := typed[jobType]
		if !ok {
			return 0
		}
		switch ids := value.(type) {
		case []string:
			return len(ids)
		case []any:
			return len(ids)
		default:
			return 0
		}
	default:
		return 0
	}
}

func childJobCount(result storage.JobRunPayload) int {
	raw, ok := result[ResultKeyChildJobIDs]
	if !ok || raw == nil {
		return 0
	}

	switch typed := raw.(type) {
	case map[string][]string:
		total := 0
		for _, ids := range typed {
			total += len(ids)
		}
		return total
	case map[string]any:
		total := 0
		for _, value := range typed {
			switch ids := value.(type) {
			case []string:
				total += len(ids)
			case []any:
				total += len(ids)
			}
		}
		return total
	default:
		return 0
	}
}
