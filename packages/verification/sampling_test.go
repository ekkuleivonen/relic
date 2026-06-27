package verification

import (
	"testing"
	"time"
)

func TestSampleRateByObjectCount(t *testing.T) {
	tests := []struct {
		name        string
		objectCount int64
		want        float64
	}{
		{name: "large", objectCount: 100_001, want: 0.01},
		{name: "large boundary", objectCount: 100_000, want: 0.10},
		{name: "medium", objectCount: 50_000, want: 0.10},
		{name: "medium lower boundary", objectCount: 10_000, want: 0.10},
		{name: "small", objectCount: 9_999, want: 0.25},
		{name: "empty scope", objectCount: 0, want: 0.25},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := SampleRate(tt.objectCount); got != tt.want {
				t.Fatalf("SampleRate(%d) = %v, want %v", tt.objectCount, got, tt.want)
			}
		})
	}
}

func TestDailyEpochTruncatesToUTCDate(t *testing.T) {
	input := time.Date(2026, 6, 27, 15, 30, 0, 0, time.FixedZone("JST", 9*60*60))
	got := DailyEpoch(input)
	want := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	if !got.Equal(want) {
		t.Fatalf("DailyEpoch() = %v, want %v", got, want)
	}
}

func TestShouldSampleIsDeterministicWithinEpoch(t *testing.T) {
	partition := PartitionFromIndex(42, DefaultModulus)
	epoch := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	rate := 0.25

	first := ShouldSample(partition, rate, epoch)
	second := ShouldSample(partition, rate, epoch)
	if first != second {
		t.Fatalf("ShouldSample not deterministic: first=%v second=%v", first, second)
	}
}

func TestShouldSampleRotatesAcrossEpochs(t *testing.T) {
	partition := PartitionFromIndex(42, DefaultModulus)
	rate := 0.50

	dayOne := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	dayTwo := time.Date(2026, 6, 28, 0, 0, 0, 0, time.UTC)

	seenDifferent := false
	for index := uint32(0); index < DefaultModulus; index++ {
		p := PartitionFromIndex(index, DefaultModulus)
		if ShouldSample(p, rate, dayOne) != ShouldSample(p, rate, dayTwo) {
			seenDifferent = true
			break
		}
	}
	if !seenDifferent {
		t.Fatal("expected at least one partition to change sampling decision across epochs")
	}

	_ = ShouldSample(partition, rate, dayOne)
}

func TestShouldSampleAlwaysIncludesAtFullRate(t *testing.T) {
	partition := PartitionFromIndex(1, DefaultModulus)
	epoch := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	if !ShouldSample(partition, 1.0, epoch) {
		t.Fatal("ShouldSample with rate 1.0 returned false")
	}
}

func TestShouldSampleNeverIncludesAtZeroRate(t *testing.T) {
	partition := PartitionFromIndex(1, DefaultModulus)
	epoch := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	if ShouldSample(partition, 0, epoch) {
		t.Fatal("ShouldSample with rate 0 returned true")
	}
}

func TestSamplePartitionsScansAllForSmallScopes(t *testing.T) {
	epoch := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	partitions := SamplePartitions(DefaultModulus, 500, epoch)
	if len(partitions) != int(DefaultModulus) {
		t.Fatalf("len(SamplePartitions) = %d, want %d", len(partitions), DefaultModulus)
	}
}

func TestSamplePartitionsSubsetForLargeScopes(t *testing.T) {
	epoch := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	partitions := SamplePartitions(DefaultModulus, 200_000, epoch)

	wantApprox := DefaultModulus / 100 // ~2-3 partitions at 1%
	if len(partitions) == int(DefaultModulus) {
		t.Fatalf("expected subset sampling for large scope, got all %d partitions", DefaultModulus)
	}
	if len(partitions) < wantApprox/2 || len(partitions) > wantApprox*2 {
		t.Fatalf("len(SamplePartitions) = %d, want roughly %d", len(partitions), wantApprox)
	}
}

func TestSamplePartitionsReturnsSortedUniqueIndexes(t *testing.T) {
	epoch := time.Date(2026, 6, 27, 0, 0, 0, 0, time.UTC)
	partitions := SamplePartitions(DefaultModulus, 50_000, epoch)

	for i := 1; i < len(partitions); i++ {
		if partitions[i].Index <= partitions[i-1].Index {
			t.Fatalf("partitions not sorted by index: %#v", partitions)
		}
	}
}
