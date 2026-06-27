package verification

import "testing"

func TestPartitionIndexIsStable(t *testing.T) {
	key := "photos/2024/a.jpg"
	first := PartitionIndex(key, DefaultModulus)
	second := PartitionIndex(key, DefaultModulus)
	if first != second {
		t.Fatalf("PartitionIndex not stable: first=%d second=%d", first, second)
	}
}

func TestPartitionIndexStaysWithinModulus(t *testing.T) {
	keys := []string{
		"readme.txt",
		"photos/2024/a.jpg",
		"objects/0000000001.bin",
		"logs/2026/06/27/app.log",
	}
	for _, key := range keys {
		index := PartitionIndex(key, DefaultModulus)
		if index >= DefaultModulus {
			t.Fatalf("PartitionIndex(%q) = %d, want < %d", key, index, DefaultModulus)
		}
	}
}

func TestPartitionIndexRejectsZeroModulus(t *testing.T) {
	defer func() {
		if recover() == nil {
			t.Fatal("PartitionIndex with zero modulus did not panic")
		}
	}()
	_ = PartitionIndex("photos/a.jpg", 0)
}

func TestPartitionIDFormat(t *testing.T) {
	partition := PartitionFromIndex(42, 256)
	if got, want := partition.ID(), "042/256"; got != want {
		t.Fatalf("ID() = %q, want %q", got, want)
	}
}

func TestParsePartitionIDRoundTrip(t *testing.T) {
	partition := PartitionFromIndex(7, DefaultModulus)
	parsed, err := ParsePartitionID(partition.ID())
	if err != nil {
		t.Fatalf("ParsePartitionID returned error: %v", err)
	}
	if parsed != partition {
		t.Fatalf("parsed partition = %#v, want %#v", parsed, partition)
	}
}

func TestParsePartitionIDRejectsInvalidInput(t *testing.T) {
	tests := []struct {
		name  string
		input string
	}{
		{name: "empty", input: ""},
		{name: "missing modulus", input: "042"},
		{name: "non numeric index", input: "abc/256"},
		{name: "wrong scheme fields", input: "042/256/extra"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := ParsePartitionID(tt.input); err == nil {
				t.Fatalf("ParsePartitionID(%q) returned nil error", tt.input)
			}
		})
	}
}

func TestPartitionForKey(t *testing.T) {
	key := "data/file.bin"
	wantIndex := PartitionIndex(key, DefaultModulus)
	partition := PartitionForKey(key, DefaultModulus)
	if partition.Index != wantIndex {
		t.Fatalf("Index = %d, want %d", partition.Index, wantIndex)
	}
	if partition.Modulus != DefaultModulus {
		t.Fatalf("Modulus = %d, want %d", partition.Modulus, DefaultModulus)
	}
	if partition.Scheme != SchemeHash {
		t.Fatalf("Scheme = %q, want %q", partition.Scheme, SchemeHash)
	}
}

func TestAllPartitionsReturnsFullRange(t *testing.T) {
	partitions := AllPartitions(4)
	if len(partitions) != 4 {
		t.Fatalf("len(AllPartitions(4)) = %d, want 4", len(partitions))
	}
	for i, partition := range partitions {
		if partition.Index != uint32(i) {
			t.Fatalf("partitions[%d].Index = %d, want %d", i, partition.Index, i)
		}
		if partition.Modulus != 4 {
			t.Fatalf("partitions[%d].Modulus = %d, want 4", i, partition.Modulus)
		}
	}
}
