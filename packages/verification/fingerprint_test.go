package verification

import "testing"

func TestAccumulatorTracksCountAndBytes(t *testing.T) {
	accumulator := &Accumulator{}
	accumulator.AddObject(100)
	accumulator.AddObject(250)

	fingerprint := accumulator.Snapshot()
	if fingerprint.Count != 2 {
		t.Fatalf("Count = %d, want 2", fingerprint.Count)
	}
	if fingerprint.Bytes != 350 {
		t.Fatalf("Bytes = %d, want 350", fingerprint.Bytes)
	}
}

func TestAccumulatorEmpty(t *testing.T) {
	accumulator := &Accumulator{}
	if !accumulator.Empty() {
		t.Fatal("new Accumulator reported non-empty")
	}

	accumulator.AddObject(10)
	if accumulator.Empty() {
		t.Fatal("Accumulator with objects reported empty")
	}
}

func TestCompareFingerprintsMatchesEqualSnapshots(t *testing.T) {
	local := Fingerprint{Count: 3, Bytes: 900}
	upstream := Fingerprint{Count: 3, Bytes: 900}

	result := CompareFingerprints(local, upstream)
	if !result.Match {
		t.Fatalf("Match = false, want true (drift at %q)", result.DriftAt)
	}
	if result.DriftAt != "" {
		t.Fatalf("DriftAt = %q, want empty", result.DriftAt)
	}
}

func TestCompareFingerprintsShortCircuitsOnCount(t *testing.T) {
	local := Fingerprint{Count: 2, Bytes: 100}
	upstream := Fingerprint{Count: 3, Bytes: 100}

	result := CompareFingerprints(local, upstream)
	if result.Match {
		t.Fatal("Match = true, want false")
	}
	if result.DriftAt != DriftAtCount {
		t.Fatalf("DriftAt = %q, want %q", result.DriftAt, DriftAtCount)
	}
}

func TestCompareFingerprintsShortCircuitsOnBytes(t *testing.T) {
	local := Fingerprint{Count: 2, Bytes: 100}
	upstream := Fingerprint{Count: 2, Bytes: 200}

	result := CompareFingerprints(local, upstream)
	if result.Match {
		t.Fatal("Match = true, want false")
	}
	if result.DriftAt != DriftAtBytes {
		t.Fatalf("DriftAt = %q, want %q", result.DriftAt, DriftAtBytes)
	}
}

func TestPartitionAccumulatorsRoutesByKey(t *testing.T) {
	modulus := uint32(8)
	accumulators := NewPartitionAccumulators(modulus)

	accumulators.AddKey("photos/a.jpg", 100)
	accumulators.AddKey("logs/b.log", 200)

	indexA := PartitionIndex("photos/a.jpg", modulus)
	indexB := PartitionIndex("logs/b.log", modulus)

	if got := accumulators.Snapshot(indexA).Count; got != 1 {
		t.Fatalf("partition %d Count = %d, want 1", indexA, got)
	}
	if got := accumulators.Snapshot(indexB).Bytes; got != 200 {
		t.Fatalf("partition %d Bytes = %d, want 200", indexB, got)
	}
}

func TestPartitionAccumulatorsEmpty(t *testing.T) {
	accumulators := NewPartitionAccumulators(4)
	if !accumulators.Empty(0) {
		t.Fatal("Empty(0) = false, want true")
	}

	accumulators.AddKey("file.txt", 10)
	if accumulators.Empty(PartitionIndex("file.txt", 4)) {
		t.Fatal("Empty after AddKey = true, want false")
	}
}
