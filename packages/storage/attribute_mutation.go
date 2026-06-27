package storage

import (
	"context"
	"fmt"
	"strings"
)

const UserAttributePrefix = "user"

type AttributeMutation struct {
	AllowedPrefix string
	Sets          map[string]any
	Deletes       []string
	Provenance    map[string]string
}

func (s *ObjectStore) MutateObjectAttributes(ctx context.Context, objectID string, mutation AttributeMutation) (Object, error) {
	object, err := s.GetObject(ctx, objectID)
	if err != nil {
		return Object{}, err
	}

	prefix := mutation.AllowedPrefix
	if prefix == "" {
		prefix = UserAttributePrefix
	}

	for path := range mutation.Sets {
		if err := validateMutationPath(prefix, path); err != nil {
			return Object{}, err
		}
	}
	for _, path := range mutation.Deletes {
		if err := validateMutationPath(prefix, path); err != nil {
			return Object{}, err
		}
	}

	if err := validateMutationCatalogTypes(ctx, s.runner, mutation.Sets); err != nil {
		return Object{}, err
	}

	attributes := cloneObjectAttributes(object.Attributes)
	for path, value := range mutation.Sets {
		if err := setAttributeAtPath(attributes, path, value); err != nil {
			return Object{}, fmt.Errorf("mutate object attributes: %w", err)
		}
	}
	for _, path := range mutation.Deletes {
		if err := deleteAttributeAtPath(attributes, path); err != nil {
			return Object{}, fmt.Errorf("mutate object attributes: %w", err)
		}
	}

	provenance := cloneObjectAttributeProvenance(object.AttributeProvenance)
	for path, ref := range mutation.Provenance {
		provenance[path] = ref
	}
	for _, path := range mutation.Deletes {
		delete(provenance, path)
	}

	encodedAttributes, err := encodeObjectAttributes(attributes)
	if err != nil {
		return Object{}, err
	}
	encodedProvenance, err := encodeObjectAttributeProvenance(provenance)
	if err != nil {
		return Object{}, err
	}

	updated, err := scanObject(s.runner.QueryRow(ctx, `
		UPDATE objects
		SET
			attributes = $2,
			attribute_provenance = $3,
			updated_at = now()
		WHERE id = $1
		RETURNING
			id,
			bucket_id,
			key,
			attributes,
			attribute_provenance,
			created_at,
			updated_at
	`, objectID, encodedAttributes, encodedProvenance))
	if err != nil {
		return Object{}, fmt.Errorf("mutate object attributes: %w", err)
	}

	if err := observeAttributeCatalog(ctx, s.runner, []UpsertObjectParams{{
		BucketID:   object.BucketID,
		Key:        object.Key,
		Attributes: attributes,
	}}); err != nil {
		return Object{}, err
	}

	return updated, nil
}

func validateMutationPath(prefix, path string) error {
	path = strings.TrimSpace(path)
	if path == "" {
		return fmt.Errorf("mutate object attributes: path is required")
	}
	requiredPrefix := prefix + "."
	if !strings.HasPrefix(path, requiredPrefix) {
		return fmt.Errorf("mutate object attributes: path %q must start with %q", path, requiredPrefix)
	}
	suffix := strings.TrimPrefix(path, requiredPrefix)
	if suffix == "" || strings.Contains(suffix, "..") {
		return fmt.Errorf("mutate object attributes: path %q is invalid", path)
	}

	return nil
}

func validateMutationCatalogTypes(ctx context.Context, runner Runner, sets map[string]any) error {
	if len(sets) == 0 {
		return nil
	}

	catalog := NewAttributeCatalogStore(runner)
	for path, value := range sets {
		typ, ok := inferCatalogValueType(value)
		if !ok {
			continue
		}

		entry, exists, err := catalog.Resolve(ctx, path)
		if err != nil {
			return err
		}
		if !exists {
			continue
		}

		_, compatible := widenCatalogValueType(entry.ValueType, typ)
		if !compatible {
			return fmt.Errorf("mutate object attributes path %q: %w", path, ErrCatalogTypeConflict)
		}
	}

	return nil
}

func setAttributeAtPath(attributes ObjectAttributes, path string, value any) error {
	parts := splitAttributePath(path)
	if len(parts) == 0 {
		return fmt.Errorf("set attribute path: path is empty")
	}

	root, ok := asNestedAttributeMap(attributes)
	if !ok {
		return fmt.Errorf("set attribute path %q: root is not an object", path)
	}

	current := root
	for _, part := range parts[:len(parts)-1] {
		next, ok := current[part]
		if !ok {
			next = map[string]any{}
			current[part] = next
		}

		child, ok := asNestedAttributeMap(next)
		if !ok {
			child = map[string]any{}
			current[part] = child
		}

		current = child
	}

	current[parts[len(parts)-1]] = value
	return nil
}

func deleteAttributeAtPath(attributes ObjectAttributes, path string) error {
	parts := splitAttributePath(path)
	if len(parts) == 0 {
		return fmt.Errorf("delete attribute path: path is empty")
	}

	root, ok := asNestedAttributeMap(attributes)
	if !ok {
		return nil
	}

	current := root
	parents := []map[string]any{root}
	parentKeys := []string{}

	for _, part := range parts[:len(parts)-1] {
		next, ok := current[part]
		if !ok {
			return nil
		}

		child, ok := asNestedAttributeMap(next)
		if !ok {
			return nil
		}

		parents = append(parents, child)
		parentKeys = append(parentKeys, part)
		current = child
	}

	delete(current, parts[len(parts)-1])

	for index := len(parents) - 1; index > 0; index-- {
		if len(parents[index]) > 0 {
			break
		}
		delete(parents[index-1], parentKeys[index-1])
	}

	return nil
}

func asNestedAttributeMap(value any) (map[string]any, bool) {
	switch typed := value.(type) {
	case ObjectAttributes:
		return map[string]any(typed), true
	case map[string]any:
		return typed, true
	default:
		return nil, false
	}
}

func cloneObjectAttributeProvenance(provenance ObjectAttributeProvenance) ObjectAttributeProvenance {
	if provenance == nil {
		return ObjectAttributeProvenance{}
	}

	cloned := ObjectAttributeProvenance{}
	for path, ref := range provenance {
		cloned[path] = ref
	}

	return cloned
}
