package verification

import (
	"hash/fnv"
	"time"
)

const (
	largeScopeObjectThreshold  int64 = 100_000
	mediumScopeObjectThreshold int64 = 10_000
)

func SampleRate(objectCount int64) float64 {
	switch {
	case objectCount > largeScopeObjectThreshold:
		return 0.01
	case objectCount >= mediumScopeObjectThreshold:
		return 0.10
	default:
		return 0.25
	}
}

func DailyEpoch(value time.Time) time.Time {
	value = value.UTC()
	return time.Date(value.Year(), value.Month(), value.Day(), 0, 0, 0, 0, time.UTC)
}

func ShouldSample(partition Partition, rate float64, epoch time.Time) bool {
	switch {
	case rate >= 1:
		return true
	case rate <= 0:
		return false
	}

	hasher := fnv.New32a()
	_, _ = hasher.Write([]byte(partition.ID()))
	_, _ = hasher.Write([]byte(DailyEpoch(epoch).Format(time.DateOnly)))

	return hasher.Sum32()%10_000 < uint32(rate*10_000)
}

func SamplePartitions(modulus uint32, objectCount int64, epoch time.Time) []Partition {
	if objectCount < mediumScopeObjectThreshold {
		return AllPartitions(modulus)
	}

	rate := SampleRate(objectCount)
	partitions := []Partition{}
	for index := uint32(0); index < modulus; index++ {
		partition := PartitionFromIndex(index, modulus)
		if ShouldSample(partition, rate, epoch) {
			partitions = append(partitions, partition)
		}
	}

	return partitions
}
