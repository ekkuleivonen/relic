package upstreamprocessor

import "testing"

func TestKeyInBucketScope(t *testing.T) {
	tests := []struct {
		bucketPrefix string
		key          string
		want         bool
	}{
		{bucketPrefix: "", key: "photos/a.jpg", want: true},
		{bucketPrefix: "raw/", key: "raw/photos/a.jpg", want: true},
		{bucketPrefix: "raw/", key: "other/a.jpg", want: false},
	}

	for _, test := range tests {
		got := KeyInBucketScope(test.bucketPrefix, test.key)
		if got != test.want {
			t.Fatalf("KeyInBucketScope(%q, %q) = %v, want %v", test.bucketPrefix, test.key, got, test.want)
		}
	}
}
