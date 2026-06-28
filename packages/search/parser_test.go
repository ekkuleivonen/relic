package search

import (
	"testing"
	"time"
)

func TestParseFromObjects(t *testing.T) {
	query, err := Parse("FROM objects")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
	}
	assertQueryEqual(t, query, want)
}

func TestParseFromRelations(t *testing.T) {
	query, err := Parse("FROM relations")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetRelations,
	}
	assertQueryEqual(t, query, want)
}

func TestParseFieldPredicate(t *testing.T) {
	query, err := Parse("FROM objects WHERE key = 'foo.txt'")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op:    OpEq,
			Left:  FieldRef{Name: "key"},
			Right: StringLiteral{Value: "foo.txt"},
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseAttributePredicatesOrderAndLimit(t *testing.T) {
	query, err := Parse(`
		FROM objects
		WHERE attr('upstream.size') >= 1048576
		  AND attr('upstream.header.content_type') = 'application/pdf'
		ORDER BY attr('upstream.last_modified') DESC
		LIMIT 100
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &BoolExpr{
			Op: BoolAnd,
			Terms: []Expr{
				Comparison{
					Op:    OpGte,
					Left:  AttrRef{Path: "upstream.size"},
					Right: IntLiteral{Value: 1048576},
				},
				Comparison{
					Op:    OpEq,
					Left:  AttrRef{Path: "upstream.header.content_type"},
					Right: StringLiteral{Value: "application/pdf"},
				},
			},
		},
		OrderBy: []OrderExpr{
			{
				Expr:      AttrRef{Path: "upstream.last_modified"},
				Direction: SortDesc,
			},
		},
		Limit: intPtr(100),
	}
	assertQueryEqual(t, query, want)
}

func TestParseQueryStructureWithAllClauses(t *testing.T) {
	query, err := Parse(`
		FROM objects
		WHERE key LIKE 'photos/%'
		ORDER BY key ASC
		LIMIT 25
		OFFSET 50
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op:    OpLike,
			Left:  FieldRef{Name: "key"},
			Right: StringLiteral{Value: "photos/%"},
		},
		OrderBy: []OrderExpr{
			{
				Expr:      FieldRef{Name: "key"},
				Direction: SortAsc,
			},
		},
		Limit:  intPtr(25),
		Offset: intPtr(50),
	}
	assertQueryEqual(t, query, want)
}

func TestParseQueryStructureWithOptionalClauses(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  Query
	}{
		{
			name:  "from only",
			input: "FROM objects",
			want: Query{
				Version: VersionV1,
				From:    TargetObjects,
			},
		},
		{
			name:  "order only",
			input: "FROM objects ORDER BY key DESC",
			want: Query{
				Version: VersionV1,
				From:    TargetObjects,
				OrderBy: []OrderExpr{
					{
						Expr:      FieldRef{Name: "key"},
						Direction: SortDesc,
					},
				},
			},
		},
		{
			name:  "limit only",
			input: "FROM objects LIMIT 10",
			want: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Limit:   intPtr(10),
			},
		},
		{
			name:  "offset only",
			input: "FROM objects OFFSET 20",
			want: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Offset:  intPtr(20),
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			query, err := Parse(tt.input)
			if err != nil {
				t.Fatalf("Parse returned error: %v", err)
			}
			assertQueryEqual(t, query, tt.want)
		})
	}
}

func TestParseBuiltInFieldReferences(t *testing.T) {
	fields := []string{
		"id",
		"bucket_id",
		"key",
		"created_at",
		"updated_at",
	}

	for _, field := range fields {
		t.Run(field, func(t *testing.T) {
			query, err := Parse("FROM objects WHERE " + field + " = 'value' ORDER BY " + field)
			if err != nil {
				t.Fatalf("Parse returned error: %v", err)
			}

			want := Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpEq,
					Left:  FieldRef{Name: field},
					Right: StringLiteral{Value: "value"},
				},
				OrderBy: []OrderExpr{
					{
						Expr:      FieldRef{Name: field},
						Direction: SortAsc,
					},
				},
			}
			assertQueryEqual(t, query, want)
		})
	}
}

func TestParseAllowsUnknownFieldReferences(t *testing.T) {
	tests := []string{
		"FROM objects WHERE unknown = 'value'",
		"FROM objects ORDER BY unknown",
		"FROM relations WHERE relation_type = 'duplicate'",
	}

	for _, input := range tests {
		t.Run(input, func(t *testing.T) {
			if _, err := Parse(input); err != nil {
				t.Fatalf("Parse returned error: %v", err)
			}
		})
	}
}

func TestParseAttributePathEscapedQuote(t *testing.T) {
	query, err := Parse("FROM objects WHERE attr('user.owner''s_team') = 'finance'")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op:    OpEq,
			Left:  AttrRef{Path: "user.owner's_team"},
			Right: StringLiteral{Value: "finance"},
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseRejectsInvalidAttributePaths(t *testing.T) {
	tests := []string{
		"FROM objects WHERE attr('') = 'value'",
		"FROM objects WHERE attr('   ') = 'value'",
		"FROM objects WHERE attr('.upstream.size') = 'value'",
		"FROM objects WHERE attr('upstream..size') = 'value'",
		"FROM objects WHERE attr('upstream.size.') = 'value'",
		"FROM objects WHERE attr('upstream. size') = 'value'",
	}

	for _, input := range tests {
		t.Run(input, func(t *testing.T) {
			if _, err := Parse(input); err == nil {
				t.Fatal("Parse returned nil error")
			}
		})
	}
}

func TestParseRejectsUnterminatedAttributePathString(t *testing.T) {
	if _, err := Parse("FROM objects WHERE attr('upstream.size) = 'value'"); err == nil {
		t.Fatal("Parse returned nil error")
	}
}

func TestParseLiterals(t *testing.T) {
	timestamp := time.Date(2026, 6, 26, 0, 0, 0, 0, time.UTC)
	tests := []struct {
		name    string
		literal string
		want    Expr
	}{
		{
			name:    "string",
			literal: "'finance'",
			want:    StringLiteral{Value: "finance"},
		},
		{
			name:    "escaped string quote",
			literal: "'Bob''s file'",
			want:    StringLiteral{Value: "Bob's file"},
		},
		{
			name:    "integer",
			literal: "1048576",
			want:    IntLiteral{Value: 1048576},
		},
		{
			name:    "float",
			literal: "12.75",
			want:    FloatLiteral{Value: 12.75},
		},
		{
			name:    "true",
			literal: "true",
			want:    BoolLiteral{Value: true},
		},
		{
			name:    "false",
			literal: "false",
			want:    BoolLiteral{Value: false},
		},
		{
			name:    "timestamp",
			literal: "timestamp '2026-06-26T00:00:00Z'",
			want:    TimestampLiteral{Value: timestamp},
		},
		{
			name:    "null",
			literal: "NULL",
			want:    NullLiteral{},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			query, err := Parse("FROM objects WHERE attr('user.value') = " + tt.literal)
			if err != nil {
				t.Fatalf("Parse returned error: %v", err)
			}

			want := Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpEq,
					Left:  AttrRef{Path: "user.value"},
					Right: tt.want,
				},
			}
			assertQueryEqual(t, query, want)
		})
	}
}

func TestParseComparisonOperators(t *testing.T) {
	tests := []struct {
		name     string
		operator string
		wantOp   ComparisonOp
	}{
		{name: "equals", operator: "=", wantOp: OpEq},
		{name: "not equals bang", operator: "!=", wantOp: OpNeq},
		{name: "not equals angle", operator: "<>", wantOp: OpNeq},
		{name: "less than", operator: "<", wantOp: OpLt},
		{name: "less than or equals", operator: "<=", wantOp: OpLte},
		{name: "greater than", operator: ">", wantOp: OpGt},
		{name: "greater than or equals", operator: ">=", wantOp: OpGte},
		{name: "like", operator: "LIKE", wantOp: OpLike},
		{name: "ilike", operator: "ILIKE", wantOp: OpILike},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			query, err := Parse("FROM objects WHERE attr('user.value') " + tt.operator + " 'needle'")
			if err != nil {
				t.Fatalf("Parse returned error: %v", err)
			}

			want := Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    tt.wantOp,
					Left:  AttrRef{Path: "user.value"},
					Right: StringLiteral{Value: "needle"},
				},
			}
			assertQueryEqual(t, query, want)
		})
	}
}

func TestParseInComparison(t *testing.T) {
	query, err := Parse("FROM objects WHERE attr('user.owner') IN ('finance', 'legal', 'ops')")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &InComparison{
			Left: AttrRef{Path: "user.owner"},
			Values: []Expr{
				StringLiteral{Value: "finance"},
				StringLiteral{Value: "legal"},
				StringLiteral{Value: "ops"},
			},
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseBetweenComparison(t *testing.T) {
	query, err := Parse("FROM objects WHERE attr('upstream.size') BETWEEN 1024 AND 4096")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &BetweenComparison{
			Left:  AttrRef{Path: "upstream.size"},
			Lower: IntLiteral{Value: 1024},
			Upper: IntLiteral{Value: 4096},
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseNullComparisons(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  NullComparison
	}{
		{
			name:  "is null",
			input: "FROM objects WHERE attr('user.owner') IS NULL",
			want: NullComparison{
				Left: AttrRef{Path: "user.owner"},
			},
		},
		{
			name:  "is not null",
			input: "FROM objects WHERE attr('user.owner') IS NOT NULL",
			want: NullComparison{
				Left: AttrRef{Path: "user.owner"},
				Not:  true,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			query, err := Parse(tt.input)
			if err != nil {
				t.Fatalf("Parse returned error: %v", err)
			}

			want := Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where:   &tt.want,
			}
			assertQueryEqual(t, query, want)
		})
	}
}

func TestParseRejectsMalformedSpecialComparisons(t *testing.T) {
	tests := []string{
		"FROM objects WHERE attr('user.owner') IN ()",
		"FROM objects WHERE attr('user.owner') IN 'finance'",
		"FROM objects WHERE attr('upstream.size') BETWEEN 1024",
		"FROM objects WHERE attr('upstream.size') BETWEEN 1024 OR 4096",
		"FROM objects WHERE attr('user.owner') IS FALSE",
		"FROM objects WHERE attr('user.owner') IS NOT FALSE",
	}

	for _, input := range tests {
		t.Run(input, func(t *testing.T) {
			if _, err := Parse(input); err == nil {
				t.Fatal("Parse returned nil error")
			}
		})
	}
}

func TestParseBooleanAndOrPrecedence(t *testing.T) {
	query, err := Parse(`
		FROM objects
		WHERE key = 'a'
		   OR key = 'b'
		  AND bucket_id = 'bucket_123'
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &BoolExpr{
			Op: BoolOr,
			Terms: []Expr{
				Comparison{
					Op:    OpEq,
					Left:  FieldRef{Name: "key"},
					Right: StringLiteral{Value: "a"},
				},
				&BoolExpr{
					Op: BoolAnd,
					Terms: []Expr{
						Comparison{
							Op:    OpEq,
							Left:  FieldRef{Name: "key"},
							Right: StringLiteral{Value: "b"},
						},
						Comparison{
							Op:    OpEq,
							Left:  FieldRef{Name: "bucket_id"},
							Right: StringLiteral{Value: "bucket_123"},
						},
					},
				},
			},
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseBooleanNot(t *testing.T) {
	query, err := Parse("FROM objects WHERE NOT attr('user.archived') = true")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &NotExpr{
			Expr: Comparison{
				Op:    OpEq,
				Left:  AttrRef{Path: "user.archived"},
				Right: BoolLiteral{Value: true},
			},
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseBooleanParenthesesOverridePrecedence(t *testing.T) {
	query, err := Parse(`
		FROM objects
		WHERE (key = 'a' OR key = 'b')
		  AND bucket_id = 'bucket_123'
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &BoolExpr{
			Op: BoolAnd,
			Terms: []Expr{
				&BoolExpr{
					Op: BoolOr,
					Terms: []Expr{
						Comparison{
							Op:    OpEq,
							Left:  FieldRef{Name: "key"},
							Right: StringLiteral{Value: "a"},
						},
						Comparison{
							Op:    OpEq,
							Left:  FieldRef{Name: "key"},
							Right: StringLiteral{Value: "b"},
						},
					},
				},
				Comparison{
					Op:    OpEq,
					Left:  FieldRef{Name: "bucket_id"},
					Right: StringLiteral{Value: "bucket_123"},
				},
			},
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseRelationPredicate(t *testing.T) {
	query, err := Parse("FROM objects WHERE has_relation('duplicate')")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &RelationPredicate{
			Type:      "duplicate",
			Direction: RelationAny,
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseRelationPredicateWithDirection(t *testing.T) {
	query, err := Parse("FROM objects WHERE has_relation('derived_from', 'out')")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &RelationPredicate{
			Type:      "derived_from",
			Direction: RelationOut,
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseRelationPredicateWithBooleanLogic(t *testing.T) {
	query, err := Parse("FROM objects WHERE has_relation('duplicate') AND NOT has_relation('thumbnail_of', 'in')")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &BoolExpr{
			Op: BoolAnd,
			Terms: []Expr{
				RelationPredicate{
					Type:      "duplicate",
					Direction: RelationAny,
				},
				NotExpr{
					Expr: RelationPredicate{
						Type:      "thumbnail_of",
						Direction: RelationIn,
					},
				},
			},
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseBucketPredicate(t *testing.T) {
	query, err := Parse("FROM objects WHERE bucket('test-bucket')")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &BucketPredicate{
			Name: "test-bucket",
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseBucketPredicateWithBooleanLogic(t *testing.T) {
	query, err := Parse("FROM objects WHERE bucket('production') AND key LIKE 'photos/%'")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &BoolExpr{
			Op: BoolAnd,
			Terms: []Expr{
				BucketPredicate{Name: "production"},
				Comparison{
					Op:    OpLike,
					Left:  FieldRef{Name: "key"},
					Right: StringLiteral{Value: "photos/%"},
				},
			},
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseRejectsMalformedBucketPredicates(t *testing.T) {
	tests := []string{
		"FROM objects WHERE bucket()",
		"FROM objects WHERE bucket('')",
		"FROM objects WHERE bucket('  ')",
		"FROM objects WHERE bucket(123)",
		"FROM objects WHERE bucket('production'",
	}

	for _, input := range tests {
		t.Run(input, func(t *testing.T) {
			if _, err := Parse(input); err == nil {
				t.Fatal("Parse returned nil error")
			}
		})
	}
}

func TestParseRejectsMalformedRelationPredicates(t *testing.T) {
	tests := []string{
		"FROM objects WHERE has_relation()",
		"FROM objects WHERE has_relation('')",
		"FROM objects WHERE has_relation('  ')",
		"FROM objects WHERE has_relation(123)",
		"FROM objects WHERE has_relation('duplicate', 'sideways')",
		"FROM objects WHERE has_relation('duplicate', 123)",
		"FROM objects WHERE has_relation('duplicate', 'out', 'extra')",
		"FROM objects WHERE has_relation('duplicate'",
	}

	for _, input := range tests {
		t.Run(input, func(t *testing.T) {
			if _, err := Parse(input); err == nil {
				t.Fatal("Parse returned nil error")
			}
		})
	}
}

func TestParseMultipleOrderByExpressions(t *testing.T) {
	query, err := Parse(`
		FROM objects
		ORDER BY attr('upstream.last_modified') DESC, key ASC, created_at
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		OrderBy: []OrderExpr{
			{
				Expr:      AttrRef{Path: "upstream.last_modified"},
				Direction: SortDesc,
			},
			{
				Expr:      FieldRef{Name: "key"},
				Direction: SortAsc,
			},
			{
				Expr:      FieldRef{Name: "created_at"},
				Direction: SortAsc,
			},
		},
	}
	assertQueryEqual(t, query, want)
}

func TestParseRejectsMalformedOrderByExpressions(t *testing.T) {
	tests := []string{
		"FROM objects ORDER BY",
		"FROM objects ORDER BY key,",
		"FROM objects ORDER BY key,, created_at",
		"FROM objects ORDER BY key ASC DESC",
	}

	for _, input := range tests {
		t.Run(input, func(t *testing.T) {
			if _, err := Parse(input); err == nil {
				t.Fatal("Parse returned nil error")
			}
		})
	}
}

func TestParseRejectsMalformedBooleanGroups(t *testing.T) {
	tests := []string{
		"FROM objects WHERE (key = 'a'",
		"FROM objects WHERE key = 'a')",
		"FROM objects WHERE NOT",
		"FROM objects WHERE key = 'a' AND",
		"FROM objects WHERE OR key = 'a'",
	}

	for _, input := range tests {
		t.Run(input, func(t *testing.T) {
			if _, err := Parse(input); err == nil {
				t.Fatal("Parse returned nil error")
			}
		})
	}
}

func TestParseRejectsInvalidTimestampLiteral(t *testing.T) {
	if _, err := Parse("FROM objects WHERE attr('user.value') = timestamp 'not-a-timestamp'"); err == nil {
		t.Fatal("Parse returned nil error")
	}
}

func TestParseRejectsClausesOutOfOrder(t *testing.T) {
	tests := []string{
		"FROM objects LIMIT 10 WHERE key = 'foo.txt'",
		"FROM objects OFFSET 20 LIMIT 10",
		"FROM objects ORDER BY key WHERE key = 'foo.txt'",
	}

	for _, input := range tests {
		t.Run(input, func(t *testing.T) {
			if _, err := Parse(input); err == nil {
				t.Fatal("Parse returned nil error")
			}
		})
	}
}

func TestParseRejectsUnsupportedTarget(t *testing.T) {
	if _, err := Parse("FROM buckets"); err == nil {
		t.Fatal("Parse returned nil error")
	}
}

func TestParseRejectsSelectSyntax(t *testing.T) {
	if _, err := Parse("SELECT * FROM objects"); err == nil {
		t.Fatal("Parse returned nil error")
	}
}

func TestParseRejectsTrailingStatements(t *testing.T) {
	if _, err := Parse("FROM objects; DROP TABLE objects"); err == nil {
		t.Fatal("Parse returned nil error")
	}
}

func TestParseRejectsSemicolonWithoutTrailingStatement(t *testing.T) {
	if _, err := Parse("FROM objects;"); err == nil {
		t.Fatal("Parse returned nil error")
	}
}

func TestParseRejectsUnsupportedOperator(t *testing.T) {
	if _, err := Parse("FROM objects WHERE attr('upstream.size') ~~ 10"); err == nil {
		t.Fatal("Parse returned nil error")
	}
}

func assertQueryEqual(t *testing.T, got Query, want Query) {
	t.Helper()

	if diff := got.Diff(want); diff != "" {
		t.Fatalf("query mismatch (-got +want):\n%s", diff)
	}
}

func intPtr(value int) *int {
	return &value
}
