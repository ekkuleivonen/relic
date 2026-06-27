package upstreamprocessor

import "github.com/ekkuleivonen/relic/packages/storage"

type CoalesceInput struct {
	EventID  string
	BucketID string
	Key      string
	JobType  storage.JobType
	ObjectID string
}

type CoalescedMutation struct {
	BucketID string
	Key      string
	JobType  storage.JobType
	ObjectID string
	EventIDs []string
}

type MutationJobGroup struct {
	BucketID string
	JobType  storage.JobType
	Mutations []CoalescedMutation
}

func CoalesceMutations(inputs []CoalesceInput) []CoalescedMutation {
	type mutationKey struct {
		bucketID string
		key      string
	}

	orderedKeys := []mutationKey{}
	byKey := map[mutationKey]CoalescedMutation{}

	for _, input := range inputs {
		key := mutationKey{bucketID: input.BucketID, key: input.Key}
		current, exists := byKey[key]
		if !exists {
			orderedKeys = append(orderedKeys, key)
			current = CoalescedMutation{
				BucketID: input.BucketID,
				Key:      input.Key,
				EventIDs: []string{},
			}
		}

		current.JobType = input.JobType
		current.ObjectID = input.ObjectID
		current.EventIDs = append(current.EventIDs, input.EventID)
		byKey[key] = current
	}

	mutations := make([]CoalescedMutation, 0, len(orderedKeys))
	for _, key := range orderedKeys {
		mutations = append(mutations, byKey[key])
	}

	return mutations
}

func GroupMutationsByJob(mutations []CoalescedMutation) []MutationJobGroup {
	type groupKey struct {
		bucketID string
		jobType  storage.JobType
	}

	orderedKeys := []groupKey{}
	byGroup := map[groupKey]*MutationJobGroup{}

	for _, mutation := range mutations {
		key := groupKey{bucketID: mutation.BucketID, jobType: mutation.JobType}
		group, exists := byGroup[key]
		if !exists {
			orderedKeys = append(orderedKeys, key)
			group = &MutationJobGroup{
				BucketID: mutation.BucketID,
				JobType:  mutation.JobType,
			}
			byGroup[key] = group
		}
		group.Mutations = append(group.Mutations, mutation)
	}

	groups := make([]MutationJobGroup, 0, len(orderedKeys))
	for _, key := range orderedKeys {
		groups = append(groups, *byGroup[key])
	}

	return groups
}
