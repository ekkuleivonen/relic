package search

import (
	"strings"
	"testing"
)

func TestParseRejectsUnboundedInput(t *testing.T) {
	for _, query := range []string{
		strings.Repeat(" ", MaxQueryBytes+1),
		"FROM objects WHERE " + strings.Repeat("NOT ", 100) + "key = 'a'",
		"FROM objects WHERE " + strings.Repeat("(", 100) + "key = 'a'" + strings.Repeat(")", 100),
	} {
		if _, err := Parse(query); err == nil {
			t.Fatal("accepted oversized or deeply nested query")
		}
	}
}
