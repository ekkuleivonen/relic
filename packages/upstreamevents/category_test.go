package upstreamevents

import "testing"

func TestEventCategory(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  string
	}{
		{name: "s3 created", input: "ObjectCreated:Put", want: EventCategoryCreated},
		{name: "s3 removed", input: "ObjectRemoved:Delete", want: EventCategoryRemoved},
		{name: "tagging", input: "ObjectTagging:Put", want: EventCategoryMetadataChanged},
		{name: "other", input: "SomethingElse", want: EventCategoryOther},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if got := EventCategory(tc.input); got != tc.want {
				t.Fatalf("EventCategory(%q) = %q, want %q", tc.input, got, tc.want)
			}
		})
	}
}
