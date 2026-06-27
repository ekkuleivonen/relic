package verification

import (
	"fmt"
	"hash/fnv"
	"strconv"
	"strings"
)

const (
	SchemeHash     = "hash"
	DefaultModulus = 256
)

type Partition struct {
	Scheme  string
	Modulus uint32
	Index   uint32
}

// PartitionIndex assigns a key to a verification partition using FNV-1a 32-bit.
// This hash is a stable contract: partition assignments, stored job inputs, and
// escalation payloads all depend on it. To change the algorithm, introduce a
// new partition scheme identifier rather than altering this function in place.
func PartitionIndex(key string, modulus uint32) uint32 {
	if modulus == 0 {
		panic("verification: partition modulus must be greater than zero")
	}

	hasher := fnv.New32a()
	_, _ = hasher.Write([]byte(key))

	return hasher.Sum32() % modulus
}

func PartitionFromIndex(index, modulus uint32) Partition {
	return Partition{
		Scheme:  SchemeHash,
		Modulus: modulus,
		Index:   index,
	}
}

func PartitionForKey(key string, modulus uint32) Partition {
	return PartitionFromIndex(PartitionIndex(key, modulus), modulus)
}

func (p Partition) ID() string {
	width := partitionIDWidth(p.Modulus)
	return fmt.Sprintf("%0*d/%d", width, p.Index, p.Modulus)
}

func ParsePartitionID(id string) (Partition, error) {
	parts := strings.Split(id, "/")
	if len(parts) != 2 {
		return Partition{}, fmt.Errorf("parse partition id %q: expected index/modulus", id)
	}

	index, err := strconv.ParseUint(parts[0], 10, 32)
	if err != nil {
		return Partition{}, fmt.Errorf("parse partition id %q: invalid index: %w", id, err)
	}

	modulus, err := strconv.ParseUint(parts[1], 10, 32)
	if err != nil {
		return Partition{}, fmt.Errorf("parse partition id %q: invalid modulus: %w", id, err)
	}
	if modulus == 0 {
		return Partition{}, fmt.Errorf("parse partition id %q: modulus must be greater than zero", id)
	}
	if index >= modulus {
		return Partition{}, fmt.Errorf("parse partition id %q: index out of range", id)
	}

	return Partition{
		Scheme:  SchemeHash,
		Modulus: uint32(modulus),
		Index:   uint32(index),
	}, nil
}

func AllPartitions(modulus uint32) []Partition {
	partitions := make([]Partition, modulus)
	for index := uint32(0); index < modulus; index++ {
		partitions[index] = PartitionFromIndex(index, modulus)
	}

	return partitions
}

func partitionIDWidth(modulus uint32) int {
	if modulus == 0 {
		return 1
	}

	width := 0
	for value := modulus - 1; value > 0; value /= 10 {
		width++
	}
	if width == 0 {
		return 1
	}

	return width
}
