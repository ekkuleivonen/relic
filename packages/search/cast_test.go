package search

import (
	"testing"
	"time"
)

func TestParseCastType(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		want    ValueType
		wantErr bool
	}{
		{name: "integer", input: "integer", want: TypeInteger},
		{name: "bigint alias", input: "bigint", want: TypeInteger},
		{name: "text alias", input: "text", want: TypeString},
		{name: "timestamptz alias", input: "timestamptz", want: TypeTimestamp},
		{name: "date alias", input: "date", want: TypeTimestamp},
		{name: "unsupported", input: "jsonb", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseCastType(tt.input)
			if tt.wantErr {
				if err == nil {
					t.Fatal("ParseCastType returned nil error")
				}
				return
			}
			if err != nil {
				t.Fatalf("ParseCastType returned error: %v", err)
			}
			if got != tt.want {
				t.Fatalf("type = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestParseAttributePostfixCast(t *testing.T) {
	query, err := Parse(`
		FROM objects
		WHERE attr('user.score')::integer >= 100
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op: OpGte,
			Left: CastExpr{
				Expr: AttrRef{Path: "user.score"},
				Type: TypeInteger,
			},
			Right: IntLiteral{Value: 100},
		},
	}

	assertQueryEqual(t, query, want)
}

func TestParseCastCallSyntax(t *testing.T) {
	query, err := Parse(`
		FROM objects
		WHERE CAST(attr('user.owner') AS text) LIKE 'finance%'
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op: OpLike,
			Left: CastExpr{
				Expr: AttrRef{Path: "user.owner"},
				Type: TypeString,
			},
			Right: StringLiteral{Value: "finance%"},
		},
	}

	assertQueryEqual(t, query, want)
}

func TestParseDateLiteralAndStringDateCast(t *testing.T) {
	query, err := Parse(`
		FROM objects
		WHERE attr('upstream.last_modified') >= date '2026-06-26'
		  AND attr('upstream.last_modified') < '2026-06-27'::date
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	wantTimeLower := mustParseTime(t, "2026-06-26T00:00:00Z")
	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &BoolExpr{
			Op: BoolAnd,
			Terms: []Expr{
				Comparison{
					Op:    OpGte,
					Left:  AttrRef{Path: "upstream.last_modified"},
					Right: TimestampLiteral{Value: wantTimeLower},
				},
				Comparison{
					Op:   OpLt,
					Left: AttrRef{Path: "upstream.last_modified"},
					Right: CastExpr{
						Expr: StringLiteral{Value: "2026-06-27"},
						Type: TypeTimestamp,
					},
				},
			},
		},
	}

	assertQueryEqual(t, query, want)
}

func TestParseRejectsInvalidCastType(t *testing.T) {
	if _, err := Parse("FROM objects WHERE attr('user.score')::jsonb >= 100"); err == nil {
		t.Fatal("Parse returned nil error")
	}
}

func TestBindExplicitCastOnUnknownAttribute(t *testing.T) {
	query, err := Parse(`
		FROM objects
		WHERE attr('user.score')::integer >= 100
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	if len(bound.Dependencies) == 0 {
		t.Fatal("dependencies are empty")
	}
}

func TestBindRejectsCastOnFieldRef(t *testing.T) {
	query, err := Parse("FROM objects WHERE key::integer = 1")
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	if _, err := Bind(query, BuiltinRegistry()); err == nil {
		t.Fatal("Bind returned nil error")
	}
}

func mustParseTime(t *testing.T, value string) time.Time {
	t.Helper()

	parsed, err := time.Parse(time.RFC3339, value)
	if err != nil {
		t.Fatalf("time.Parse returned error: %v", err)
	}

	return parsed.UTC()
}
