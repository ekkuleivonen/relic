package detect_duplicates

import (
	"context"
	"fmt"
	"sync"

	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/elei-io/pithosys/packages/upstreams/s3compat"
)

const (
	defaultHashConcurrency = 4
)

type Handler struct {
	store        *storage.Store
	secrets      secrets.Manager
	factory      s3compat.ObjectClientFactory
	hashWorkers  int
}

type HandlerOptions struct {
	Store       *storage.Store
	Secrets     secrets.Manager
	Factory     s3compat.ObjectClientFactory
	HashWorkers int
}

func NewHandler(options HandlerOptions) (*Handler, error) {
	if options.Store == nil {
		return nil, fmt.Errorf("create detect duplicates handler: storage store is required")
	}
	if options.Secrets == nil {
		return nil, fmt.Errorf("create detect duplicates handler: secrets manager is required")
	}
	if options.Factory == nil {
		return nil, fmt.Errorf("create detect duplicates handler: upstream client factory is required")
	}

	hashWorkers := options.HashWorkers
	if hashWorkers <= 0 {
		hashWorkers = defaultHashConcurrency
	}

	return &Handler{
		store:       options.Store,
		secrets:     options.Secrets,
		factory:     options.Factory,
		hashWorkers: hashWorkers,
	}, nil
}

func (h *Handler) Type() storage.JobType {
	return storage.JobTypeDetectDuplicates
}

func (h *Handler) Handle(ctx context.Context, run storage.JobRun) (storage.JobRunPayload, error) {
	input, err := ParseInput(run)
	if err != nil {
		return nil, err
	}
	scope := ScopeFromInput(input)

	groups, err := h.store.Objects().FindDuplicateCandidateGroups(ctx, scope)
	if err != nil {
		return nil, err
	}
	if err := h.updateProgress(ctx, run.ID, "finding_candidates", map[string]any{
		"candidate_groups": len(groups),
	}); err != nil {
		return nil, err
	}

	clientCache := newBucketClientCache(h.store, h.secrets, h.factory)
	relationsCreated := 0
	relationsRemoved := int64(0)
	verifiedGroups := 0
	bytesHashed := int64(0)
	objectsHashed := 0

	for groupIndex, group := range groups {
		if err := h.updateProgress(ctx, run.ID, "hashing", map[string]any{
			"candidate_groups": len(groups),
			"groups_done":      groupIndex,
		}); err != nil {
			return nil, err
		}

		objectIDs := make([]string, 0, len(group.Objects))
		for _, object := range group.Objects {
			objectIDs = append(objectIDs, object.ID)
		}

		hashes, groupBytesHashed, hashedCount, err := h.hashGroupObjects(ctx, clientCache, group, run.ID)
		if err != nil {
			return nil, err
		}
		bytesHashed += groupBytesHashed
		objectsHashed += hashedCount

		if !allHashesMatch(hashes) {
			removed, err := h.store.Relations().DeleteDuplicateRelationsBetween(ctx, storage.DeleteDuplicateRelationsBetweenParams{
				ObjectIDs: objectIDs,
			})
			if err != nil {
				return nil, err
			}
			relationsRemoved += removed
			continue
		}

		verifiedGroups++
		source := originalObject(group.Objects)
		relationAttributes := storage.RelationAttributes{
			"content_sha256": hashes[source.ID],
			"etag":           group.ETag,
			"size":           group.Size,
		}

		for _, object := range group.Objects {
			if object.ID == source.ID {
				continue
			}
			if _, err := h.store.Relations().CreateRelation(ctx, storage.CreateRelationParams{
				SourceObjectID: source.ID,
				TargetObjectID: object.ID,
				RelationType:   storage.RelationTypeDuplicate,
				Attributes:     relationAttributes,
				CreatedByType:  "job",
				CreatedByRunID: run.ID,
			}); err != nil {
				return nil, err
			}
			relationsCreated++
		}
	}

	return storage.JobRunPayload{
		"phase":              "completed",
		"scope":              scopePayload(scope),
		"candidate_groups":   len(groups),
		"verified_groups":    verifiedGroups,
		"objects_hashed":     objectsHashed,
		"bytes_hashed":       bytesHashed,
		"relations_created":  relationsCreated,
		"relations_removed":  relationsRemoved,
	}, nil
}

func (h *Handler) hashGroupObjects(
	ctx context.Context,
	clientCache *bucketClientCache,
	group storage.DuplicateCandidateGroup,
	runID string,
) (map[string]string, int64, int, error) {
	hashes := make(map[string]string, len(group.Objects))
	var (
		bytesHashed int64
		hashedCount int
	)

	type hashResult struct {
		objectID string
		hash     string
		bytes    int64
		cached   bool
	}

	results := make([]hashResult, len(group.Objects))
	work := make(chan int)
	var wg sync.WaitGroup
	var errOnce sync.Once
	var hashErr error

	workers := h.hashWorkers
	if workers > len(group.Objects) {
		workers = len(group.Objects)
	}
	if workers == 0 {
		return hashes, 0, 0, nil
	}

	for worker := 0; worker < workers; worker++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for index := range work {
				object := group.Objects[index]
				if hash, ok := cachedContentSHA256(object, group.ETag, group.Size); ok {
					results[index] = hashResult{objectID: object.ID, hash: hash, cached: true}
					continue
				}

				client, bucketName, err := clientCache.clientForObject(ctx, object.BucketID)
				if err != nil {
					errOnce.Do(func() { hashErr = err })
					return
				}

				versionID := attributeString(object.Attributes, storage.UpstreamS3VersionIDPath)
				hash, bytesRead, err := s3compat.HashObject(ctx, client, bucketName, s3compat.HeadObjectInput{
					Key:       object.Key,
					VersionID: versionID,
				})
				if err != nil {
					errOnce.Do(func() { hashErr = fmt.Errorf("hash object %q: %w", object.Key, err) })
					return
				}

				if err := h.persistContentSHA256(ctx, object, hash, runID); err != nil {
					errOnce.Do(func() { hashErr = err })
					return
				}

				results[index] = hashResult{objectID: object.ID, hash: hash, bytes: bytesRead}
			}
		}()
	}

	for index := range group.Objects {
		work <- index
	}
	close(work)
	wg.Wait()

	if hashErr != nil {
		return nil, 0, 0, hashErr
	}

	for _, result := range results {
		hashes[result.objectID] = result.hash
		if !result.cached {
			bytesHashed += result.bytes
			hashedCount++
		}
	}

	return hashes, bytesHashed, hashedCount, nil
}

func (h *Handler) persistContentSHA256(ctx context.Context, object storage.Object, hash string, runID string) error {
	provenance := cloneObjectAttributeProvenance(object.AttributeProvenance)
	provenance["extracted"] = runID

	_, err := h.store.Objects().UpsertObject(ctx, storage.UpsertObjectParams{
		BucketID:            object.BucketID,
		Key:                 object.Key,
		Attributes:          mergeExtractedContentSHA256(object, hash),
		AttributeProvenance: provenance,
	})
	if err != nil {
		return fmt.Errorf("persist content sha256 for object %q: %w", object.ID, err)
	}

	return nil
}

func allHashesMatch(hashes map[string]string) bool {
	if len(hashes) == 0 {
		return false
	}

	var first string
	for _, hash := range hashes {
		if hash == "" {
			return false
		}
		if first == "" {
			first = hash
			continue
		}
		if hash != first {
			return false
		}
	}

	return true
}

func scopePayload(scope storage.DuplicateDetectScope) map[string]any {
	return map[string]any{
		"bucket_ids": scope.BucketIDs,
		"prefixes":   scope.Prefixes,
	}
}

func (h *Handler) updateProgress(ctx context.Context, runID string, phase string, fields map[string]any) error {
	progress := storage.JobRunPayload{"phase": phase}
	for key, value := range fields {
		progress[key] = value
	}

	_, err := h.store.JobRuns().UpdateJobRunProgress(ctx, storage.UpdateJobRunProgressParams{
		ID:       runID,
		Progress: progress,
	})

	return err
}

func attributeString(attributes storage.ObjectAttributes, path string) string {
	value, ok := attributeValue(attributes, path)
	if !ok {
		return ""
	}
	text, ok := value.(string)
	if !ok {
		return ""
	}

	return text
}

func cloneObjectAttributeProvenance(provenance storage.ObjectAttributeProvenance) storage.ObjectAttributeProvenance {
	if provenance == nil {
		return storage.ObjectAttributeProvenance{}
	}

	cloned := storage.ObjectAttributeProvenance{}
	for key, value := range provenance {
		cloned[key] = value
	}

	return cloned
}

type bucketClientCache struct {
	store   *storage.Store
	secrets secrets.Manager
	factory s3compat.ObjectClientFactory

	mu      sync.Mutex
	buckets map[string]storage.Bucket
	clients map[string]s3compat.ObjectClient
}

func newBucketClientCache(store *storage.Store, secrets secrets.Manager, factory s3compat.ObjectClientFactory) *bucketClientCache {
	return &bucketClientCache{
		store:   store,
		secrets: secrets,
		factory: factory,
		buckets: map[string]storage.Bucket{},
		clients: map[string]s3compat.ObjectClient{},
	}
}

func (c *bucketClientCache) clientForObject(ctx context.Context, bucketID string) (s3compat.ObjectClient, string, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if client, ok := c.clients[bucketID]; ok {
		return client, c.buckets[bucketID].BucketName, nil
	}

	bucket, err := c.store.Buckets().GetBucket(ctx, bucketID)
	if err != nil {
		return nil, "", err
	}
	config, err := s3compat.BucketConfigFromStorage(bucket)
	if err != nil {
		return nil, "", err
	}
	credentialJSON, err := c.secrets.Decrypt(ctx, bucket.EncryptedCredentials)
	if err != nil {
		return nil, "", err
	}
	credentials, err := s3compat.ParseCredentials(credentialJSON)
	if err != nil {
		return nil, "", err
	}
	client, err := c.factory.NewClient(ctx, config, credentials)
	if err != nil {
		return nil, "", err
	}

	c.buckets[bucketID] = bucket
	c.clients[bucketID] = client

	return client, bucket.BucketName, nil
}
