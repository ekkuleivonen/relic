package storage

import (
	"context"
	"fmt"
)

type DuplicateDetectScope struct {
	BucketIDs []string
	Prefixes  []string
}

type DuplicateCandidateGroup struct {
	ETag    string
	Size    int64
	Objects []Object
}

func (s *ObjectStore) FindDuplicateCandidateGroups(ctx context.Context, scope DuplicateDetectScope) ([]DuplicateCandidateGroup, error) {
	rows, err := s.runner.Query(ctx, `
		WITH scoped AS (
			SELECT
				id,
				bucket_id,
				key,
				attributes,
				attribute_provenance,
				created_at,
				updated_at,
				attributes #>> '{upstream,etag}' AS etag,
				(attributes #>> '{upstream,size}')::bigint AS size
			FROM objects
			WHERE ($1::text[] IS NULL OR cardinality($1) = 0 OR bucket_id = ANY($1))
				AND (
					$2::text[] IS NULL
					OR cardinality($2) = 0
					OR EXISTS (
						SELECT 1
						FROM unnest($2) AS prefix(value)
						WHERE key LIKE prefix.value || '%'
					)
				)
				AND attributes #>> '{upstream,etag}' IS NOT NULL
				AND attributes #>> '{upstream,etag}' <> ''
				AND attributes #>> '{upstream,size}' IS NOT NULL
		),
		groups AS (
			SELECT etag, size
			FROM scoped
			GROUP BY etag, size
			HAVING count(*) > 1
		)
		SELECT
			scoped.etag,
			scoped.size,
			scoped.id,
			scoped.bucket_id,
			scoped.key,
			scoped.attributes,
			scoped.attribute_provenance,
			scoped.created_at,
			scoped.updated_at
		FROM scoped
		INNER JOIN groups
			ON groups.etag = scoped.etag
			AND groups.size = scoped.size
		ORDER BY scoped.etag ASC, scoped.size ASC, scoped.id ASC
	`, scope.BucketIDs, scope.Prefixes)
	if err != nil {
		return nil, fmt.Errorf("find duplicate candidate groups: %w", err)
	}
	defer rows.Close()

	grouped := []DuplicateCandidateGroup{}
	indexByKey := map[string]int{}

	for rows.Next() {
		var (
			etag             string
			size             int64
			object           Object
			attributesBytes  []byte
			provenanceBytes  []byte
		)
		if err := rows.Scan(
			&etag,
			&size,
			&object.ID,
			&object.BucketID,
			&object.Key,
			&attributesBytes,
			&provenanceBytes,
			&object.CreatedAt,
			&object.UpdatedAt,
		); err != nil {
			return nil, fmt.Errorf("find duplicate candidate groups: %w", err)
		}
		if err := decodeObjectAttributes(attributesBytes, &object.Attributes); err != nil {
			return nil, err
		}
		if err := decodeObjectAttributeProvenance(provenanceBytes, &object.AttributeProvenance); err != nil {
			return nil, err
		}
		firstSeenAt, lastSeenAt, err := coreTimestamps(object.Attributes)
		if err != nil {
			return nil, err
		}
		object.FirstSeenAt = firstSeenAt
		object.LastSeenAt = lastSeenAt

		key := etag + "\x00" + fmt.Sprintf("%d", size)
		groupIndex, ok := indexByKey[key]
		if !ok {
			indexByKey[key] = len(grouped)
			grouped = append(grouped, DuplicateCandidateGroup{
				ETag:    etag,
				Size:    size,
				Objects: []Object{object},
			})
			continue
		}
		grouped[groupIndex].Objects = append(grouped[groupIndex].Objects, object)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("find duplicate candidate groups: %w", err)
	}

	return grouped, nil
}
