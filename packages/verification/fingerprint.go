package verification

const (
	DriftAtCount  = "count"
	DriftAtBytes  = "bytes"
)

type Fingerprint struct {
	Count int64
	Bytes int64
}

type CompareResult struct {
	Match   bool
	DriftAt string
}

type Accumulator struct {
	count int64
	bytes int64
}

func (a *Accumulator) AddObject(size int64) {
	a.count++
	a.bytes += size
}

func (a *Accumulator) Empty() bool {
	return a.count == 0
}

func (a *Accumulator) Snapshot() Fingerprint {
	return Fingerprint{
		Count: a.count,
		Bytes: a.bytes,
	}
}

func CompareFingerprints(local, upstream Fingerprint) CompareResult {
	if local.Count != upstream.Count {
		return CompareResult{Match: false, DriftAt: DriftAtCount}
	}
	if local.Bytes != upstream.Bytes {
		return CompareResult{Match: false, DriftAt: DriftAtBytes}
	}

	return CompareResult{Match: true}
}

type PartitionAccumulators struct {
	partitions []Accumulator
	modulus    uint32
}

func NewPartitionAccumulators(modulus uint32) *PartitionAccumulators {
	return &PartitionAccumulators{
		partitions: make([]Accumulator, modulus),
		modulus:    modulus,
	}
}

func (p *PartitionAccumulators) AddKey(key string, size int64) {
	index := PartitionIndex(key, p.modulus)
	p.partitions[index].AddObject(size)
}

func (p *PartitionAccumulators) Empty(index uint32) bool {
	return p.partitions[index].Empty()
}

func (p *PartitionAccumulators) Snapshot(index uint32) Fingerprint {
	return p.partitions[index].Snapshot()
}
