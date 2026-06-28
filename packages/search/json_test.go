package search

import (
	"testing"
)

func TestMarshalUnmarshalQueryRoundTrip(t *testing.T) {
	fixtures := []string{
		"FROM objects",
		"FROM objects WHERE key = 'foo.txt'",
		`FROM objects WHERE attr('upstream.size') >= 1048576 AND attr('upstream.header.content_type') = 'application/pdf' ORDER BY attr('upstream.last_modified') DESC LIMIT 100`,
		`FROM objects WHERE key LIKE 'photos/%' ORDER BY key ASC LIMIT 25 OFFSET 50`,
		"FROM objects WHERE attr('user.owner') IN ('finance', 'legal', 'ops')",
		"FROM objects WHERE attr('upstream.size') BETWEEN 1024 AND 4096",
		"FROM objects WHERE attr('user.owner') IS NULL",
		"FROM objects WHERE attr('user.owner') IS NOT NULL",
		"FROM objects WHERE NOT attr('user.archived') = true",
		"FROM objects WHERE has_relation('duplicate')",
		"FROM objects WHERE has_relation('derived_from', 'out')",
		"FROM objects WHERE has_relation('duplicate') AND NOT has_relation('thumbnail_of', 'in')",
		"FROM objects WHERE bucket('production')",
		"FROM objects WHERE bucket('test-bucket') AND key = 'foo.txt'",
		`FROM objects WHERE key = 'a' OR key = 'b' AND bucket_id = 'bucket_123'`,
		`FROM objects WHERE (key = 'a' OR key = 'b') AND bucket_id = 'bucket_123'`,
		`FROM objects ORDER BY attr('upstream.last_modified') DESC, key ASC, created_at`,
		"FROM relations WHERE relation_type = 'duplicate'",
	}

	for _, input := range fixtures {
		t.Run(input, func(t *testing.T) {
			parsed, err := Parse(input)
			if err != nil {
				t.Fatalf("Parse returned error: %v", err)
			}

			data, err := MarshalQuery(parsed)
			if err != nil {
				t.Fatalf("MarshalQuery returned error: %v", err)
			}

			restored, err := UnmarshalQuery(data)
			if err != nil {
				t.Fatalf("UnmarshalQuery returned error: %v", err)
			}

			boundBefore, err := Bind(parsed, BuiltinRegistry())
			if err != nil {
				t.Fatalf("Bind parsed query returned error: %v", err)
			}
			boundAfter, err := Bind(restored, BuiltinRegistry())
			if err != nil {
				t.Fatalf("Bind restored query returned error: %v", err)
			}
			assertDependenciesEqual(t, boundAfter.Dependencies, boundBefore.Dependencies)
		})
	}
}

func TestMarshalUnmarshalComplexExpressions(t *testing.T) {
	tests := []Query{
		{
			Version: VersionV1,
			From:    TargetObjects,
			Where: CastExpr{
				Expr: AttrRef{Path: "upstream.size"},
				Type: TypeInteger,
			},
		},
		{
			Version: VersionV1,
			From:    TargetObjects,
			Where: Comparison{
				Op: OpGte,
				Left: AttrRef{Path: "upstream.last_modified"},
				Right: ArithmeticExpr{
					Op:    ArithSub,
					Left:  NowExpr{},
					Right: IntervalLiteral{Value: "7 days"},
				},
			},
		},
	}

	for _, query := range tests {
		t.Run(queryDiffLabel(query), func(t *testing.T) {
			data, err := MarshalQuery(query)
			if err != nil {
				t.Fatalf("MarshalQuery returned error: %v", err)
			}

			restored, err := UnmarshalQuery(data)
			if err != nil {
				t.Fatalf("UnmarshalQuery returned error: %v", err)
			}

			boundBefore, err := Bind(query, BuiltinRegistry())
			if err != nil {
				t.Fatalf("Bind original query returned error: %v", err)
			}
			boundAfter, err := Bind(restored, BuiltinRegistry())
			if err != nil {
				t.Fatalf("Bind restored query returned error: %v", err)
			}
			assertDependenciesEqual(t, boundAfter.Dependencies, boundBefore.Dependencies)
		})
	}
}

func queryDiffLabel(query Query) string {
	if query.Where != nil {
		return "where-expr"
	}
	return "query"
}

func assertDependenciesEqual(t *testing.T, got []Dependency, want []Dependency) {
	t.Helper()

	if len(got) != len(want) {
		t.Fatalf("dependency count = %d, want %d", len(got), len(want))
	}

	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("dependency[%d] = %#v, want %#v", i, got[i], want[i])
		}
	}
}
