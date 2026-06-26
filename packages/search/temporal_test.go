package search

import (
	"testing"
)

func TestParseIntervalValue(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		want    string
		wantErr bool
	}{
		{name: "days", input: "7 days", want: "7 days"},
		{name: "singular day", input: "1 day", want: "1 days"},
		{name: "hours case", input: "12 HOURS", want: "12 hours"},
		{name: "invalid unit", input: "7 fortnights", wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := ParseIntervalValue(tt.input)
			if tt.wantErr {
				if err == nil {
					t.Fatal("ParseIntervalValue returned nil error")
				}
				return
			}
			if err != nil {
				t.Fatalf("ParseIntervalValue returned error: %v", err)
			}
			if got != tt.want {
				t.Fatalf("value = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestParseNowAndRelativeInterval(t *testing.T) {
	query, err := Parse(`
		FROM objects
		WHERE attr('core.last_seen_at') >= now() - interval '7 days'
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op:   OpGte,
			Left: AttrRef{Path: "core.last_seen_at"},
			Right: ArithmeticExpr{
				Op:   ArithSub,
				Left: NowExpr{},
				Right: IntervalLiteral{Value: "7 days"},
			},
		},
	}

	assertQueryEqual(t, query, want)
}

func TestParseTimestampPlusInterval(t *testing.T) {
	wantTime := mustParseTime(t, "2026-06-26T00:00:00Z")
	query, err := Parse(`
		FROM objects
		WHERE created_at <= timestamp '2026-06-26T00:00:00Z' + interval '1 day'
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	want := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op:   OpLte,
			Left: FieldRef{Name: "created_at"},
			Right: ArithmeticExpr{
				Op:    ArithAdd,
				Left:  TimestampLiteral{Value: wantTime},
				Right: IntervalLiteral{Value: "1 days"},
			},
		},
	}

	assertQueryEqual(t, query, want)
}

func TestBindRelativeTimestampComparison(t *testing.T) {
	query, err := Parse(`
		FROM objects
		WHERE attr('core.last_seen_at') >= now() - interval '7 days'
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	if _, err := Bind(query, BuiltinRegistry()); err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}
}

func TestBindRejectsInvalidArithmetic(t *testing.T) {
	query, err := Parse(`
		FROM objects
		WHERE attr('upstream.size') >= now() - interval '7 days'
	`)
	if err != nil {
		t.Fatalf("Parse returned error: %v", err)
	}

	if _, err := Bind(query, BuiltinRegistry()); err == nil {
		t.Fatal("Bind returned nil error")
	}
}

func TestBindRejectsNowWithExtraArgs(t *testing.T) {
	if _, err := Parse("FROM objects WHERE attr('core.last_seen_at') >= now(1)"); err == nil {
		t.Fatal("Parse returned nil error")
	}
}
