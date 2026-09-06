package storage

import (
	"context"
	"fmt"
	"math"
	"strings"
	"time"

	"github.com/elei-io/pithosys/packages/search"
)

func observeAttributeCatalog(ctx context.Context, runner Runner, params []UpsertObjectParams) error {
	if len(params) == 0 {
		return nil
	}

	catalog := NewAttributeCatalogStore(runner)
	observed := map[string]search.ValueType{}

	for _, param := range params {
		for path, typ := range flattenObjectAttributes(param.Attributes) {
			if err := mergeObservedCatalogType(observed, path, typ); err != nil {
				return err
			}
			for _, prefix := range attributePathPrefixes(path) {
				if err := mergeObservedCatalogType(observed, prefix, search.TypeUnknown); err != nil {
					return err
				}
			}
		}
	}

	for path, typ := range observed {
		if err := catalog.UpsertObserved(ctx, path, typ); err != nil {
			return fmt.Errorf("observe attribute catalog path %q: %w", path, err)
		}
	}

	return nil
}

func mergeObservedCatalogType(observed map[string]search.ValueType, path string, typ search.ValueType) error {
	existing, ok := observed[path]
	if !ok {
		observed[path] = typ
		return nil
	}

	widened, compatible := widenCatalogValueType(existing, typ)
	if !compatible {
		return fmt.Errorf("observe attribute catalog path %q: %w", path, ErrCatalogTypeConflict)
	}

	observed[path] = widened
	return nil
}

func attributePathPrefixes(path string) []string {
	parts := splitAttributePath(path)
	if len(parts) <= 1 {
		return nil
	}

	prefixes := make([]string, 0, len(parts)-1)
	for index := 1; index < len(parts); index++ {
		prefixes = append(prefixes, strings.Join(parts[:index], "."))
	}

	return prefixes
}

func flattenObjectAttributes(attributes ObjectAttributes) map[string]search.ValueType {
	paths := map[string]search.ValueType{}
	flattenAttributeValue("", attributes, paths)
	return paths
}

func flattenAttributeValue(prefix string, value any, paths map[string]search.ValueType) {
	switch typed := value.(type) {
	case map[string]any:
		for key, child := range typed {
			path := joinAttributePath(prefix, key)
			flattenAttributeValue(path, child, paths)
		}
	case ObjectAttributes:
		for key, child := range typed {
			path := joinAttributePath(prefix, key)
			flattenAttributeValue(path, child, paths)
		}
	default:
		if prefix == "" {
			return
		}
		if typ, ok := inferCatalogValueType(value); ok {
			paths[prefix] = typ
		}
	}
}

func joinAttributePath(prefix, segment string) string {
	if prefix == "" {
		return segment
	}
	if segment == "" {
		return prefix
	}
	return prefix + "." + segment
}

func inferCatalogValueType(value any) (search.ValueType, bool) {
	switch typed := value.(type) {
	case nil:
		return "", false
	case string:
		if _, err := time.Parse(time.RFC3339, typed); err == nil {
			return search.TypeTimestamp, true
		}
		return search.TypeString, true
	case bool:
		return search.TypeBoolean, true
	case int:
		return search.TypeInteger, true
	case int8, int16, int32, int64:
		return search.TypeInteger, true
	case uint, uint8, uint16, uint32, uint64:
		return search.TypeInteger, true
	case float32:
		if float64(typed) == math.Trunc(float64(typed)) {
			return search.TypeInteger, true
		}
		return search.TypeFloat, true
	case float64:
		if typed == math.Trunc(typed) {
			return search.TypeInteger, true
		}
		return search.TypeFloat, true
	case []any, map[string]any, ObjectAttributes:
		return search.TypeUnknown, true
	default:
		return "", false
	}
}
