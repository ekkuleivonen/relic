package search

import (
	"strings"
	"testing"
	"time"
)

func TestBindObjectsTarget(t *testing.T) {
	bound, err := Bind(Query{
		Version: VersionV1,
		From:    TargetObjects,
	}, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: Query{
			Version: VersionV1,
			From:    TargetObjects,
		},
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindRejectsUnknownTarget(t *testing.T) {
	_, err := Bind(Query{
		Version: VersionV1,
		From:    Target("buckets"),
	}, BuiltinRegistry())
	if err == nil {
		t.Fatal("Bind returned nil error")
	}
}

func TestBindRelationsTarget(t *testing.T) {
	bound, err := Bind(Query{
		Version: VersionV1,
		From:    TargetRelations,
	}, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: Query{
			Version: VersionV1,
			From:    TargetRelations,
		},
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "relations"},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindAllowsTargetSpecificFields(t *testing.T) {
	tests := []struct {
		name  string
		query Query
	}{
		{
			name: "object field on objects",
			query: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpEq,
					Left:  FieldRef{Name: "key"},
					Right: StringLiteral{Value: "photos/a.jpg"},
				},
			},
		},
		{
			name: "relation field on relations",
			query: Query{
				Version: VersionV1,
				From:    TargetRelations,
				Where: &Comparison{
					Op:    OpEq,
					Left:  FieldRef{Name: "relation_type"},
					Right: StringLiteral{Value: "duplicate"},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := Bind(tt.query, BuiltinRegistry()); err != nil {
				t.Fatalf("Bind returned error: %v", err)
			}
		})
	}
}

func TestBindObjectBuiltInFieldTypes(t *testing.T) {
	tests := []struct {
		field string
		typ   ValueType
	}{
		{field: "id", typ: TypeString},
		{field: "bucket_id", typ: TypeString},
		{field: "key", typ: TypeString},
		{field: "created_at", typ: TypeTimestamp},
		{field: "updated_at", typ: TypeTimestamp},
	}

	for _, tt := range tests {
		t.Run(tt.field, func(t *testing.T) {
			query := Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpEq,
					Left:  FieldRef{Name: tt.field},
					Right: literalForType(tt.typ),
				},
			}

			bound, err := Bind(query, BuiltinRegistry())
			if err != nil {
				t.Fatalf("Bind returned error: %v", err)
			}

			want := BoundQuery{
				Query: query,
				Dependencies: []Dependency{
					{Kind: DependencyTarget, Name: "objects"},
					{Kind: DependencyField, Name: tt.field, Type: tt.typ},
				},
			}
			assertBoundQueryEqual(t, bound, want)
		})
	}
}

func TestBindRecordsOrderByFieldDependency(t *testing.T) {
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		OrderBy: []OrderExpr{
			{
				Expr:      FieldRef{Name: "updated_at"},
				Direction: SortDesc,
			},
		},
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyField, Name: "updated_at", Type: TypeTimestamp},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindOrderByKeyAscBindsStringField(t *testing.T) {
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		OrderBy: []OrderExpr{
			{
				Expr:      FieldRef{Name: "key"},
				Direction: SortAsc,
			},
		},
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyField, Name: "key", Type: TypeString},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindOrderByAttributeDescBindsAttribute(t *testing.T) {
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		OrderBy: []OrderExpr{
			{
				Expr:      AttrRef{Path: "upstream.last_modified"},
				Direction: SortDesc,
			},
		},
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyAttribute, Name: "upstream.last_modified", Type: TypeTimestamp},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindMultipleOrderTermsRecordAllDependencies(t *testing.T) {
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		OrderBy: []OrderExpr{
			{
				Expr:      FieldRef{Name: "key"},
				Direction: SortAsc,
			},
			{
				Expr:      AttrRef{Path: "upstream.last_modified"},
				Direction: SortDesc,
			},
			{
				Expr:      AttrRef{Path: "upstream.size"},
				Direction: SortDesc,
			},
		},
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyField, Name: "key", Type: TypeString},
			{Kind: DependencyAttribute, Name: "upstream.last_modified", Type: TypeTimestamp},
			{Kind: DependencyAttribute, Name: "upstream.size", Type: TypeInteger},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindUnknownOrderAttributeUsesUnknownPolicy(t *testing.T) {
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		OrderBy: []OrderExpr{
			{
				Expr:      AttrRef{Path: "user.rank"},
				Direction: SortDesc,
			},
		},
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyAttribute, Name: "user.rank", Type: TypeUnknown},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindAcceptsLimitAndOffset(t *testing.T) {
	limit := 100
	offset := 200
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Limit:   &limit,
		Offset:  &offset,
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindRejectsUnknownFieldReference(t *testing.T) {
	_, err := Bind(Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op:    OpEq,
			Left:  FieldRef{Name: "unknown"},
			Right: StringLiteral{Value: "value"},
		},
	}, BuiltinRegistry())
	if err == nil {
		t.Fatal("Bind returned nil error")
	}
}

func TestBindKnownAttributeTypes(t *testing.T) {
	tests := []struct {
		path string
		typ  ValueType
	}{
		{path: "upstream.size", typ: TypeInteger},
		{path: "upstream.last_modified", typ: TypeTimestamp},
		{path: "upstream.header.content_type", typ: TypeString},
	}

	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			query := Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpEq,
					Left:  AttrRef{Path: tt.path},
					Right: literalForType(tt.typ),
				},
			}

			bound, err := Bind(query, BuiltinRegistry())
			if err != nil {
				t.Fatalf("Bind returned error: %v", err)
			}

			want := BoundQuery{
				Query: query,
				Dependencies: []Dependency{
					{Kind: DependencyTarget, Name: "objects"},
					{Kind: DependencyAttribute, Name: tt.path, Type: tt.typ},
				},
			}
			assertBoundQueryEqual(t, bound, want)
		})
	}
}

func TestBindUnknownAttributeAsUnknownDependency(t *testing.T) {
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op:    OpEq,
			Left:  AttrRef{Path: "user.owner"},
			Right: StringLiteral{Value: "finance"},
		},
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyAttribute, Name: "user.owner", Type: TypeUnknown},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindDeduplicatesAttributeDependencies(t *testing.T) {
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &BoolExpr{
			Op: BoolAnd,
			Terms: []Expr{
				Comparison{
					Op:    OpGt,
					Left:  AttrRef{Path: "upstream.size"},
					Right: IntLiteral{Value: 1024},
				},
				Comparison{
					Op:    OpLt,
					Left:  AttrRef{Path: "upstream.size"},
					Right: IntLiteral{Value: 4096},
				},
			},
		},
		OrderBy: []OrderExpr{
			{
				Expr:      AttrRef{Path: "upstream.size"},
				Direction: SortDesc,
			},
		},
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyAttribute, Name: "upstream.size", Type: TypeInteger},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindRecordsAttributeDependenciesFromWhereAndOrderBy(t *testing.T) {
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op:    OpEq,
			Left:  AttrRef{Path: "upstream.header.content_type"},
			Right: StringLiteral{Value: "image/jpeg"},
		},
		OrderBy: []OrderExpr{
			{
				Expr:      AttrRef{Path: "upstream.last_modified"},
				Direction: SortDesc,
			},
		},
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyAttribute, Name: "upstream.header.content_type", Type: TypeString},
			{Kind: DependencyAttribute, Name: "upstream.last_modified", Type: TypeTimestamp},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindLiteralTypes(t *testing.T) {
	tests := []struct {
		name     string
		registry Registry
		query    Query
	}{
		{
			name:     "string literal",
			registry: BuiltinRegistry(),
			query: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpEq,
					Left:  AttrRef{Path: "upstream.header.content_type"},
					Right: StringLiteral{Value: "image/jpeg"},
				},
			},
		},
		{
			name:     "integer literal",
			registry: BuiltinRegistry(),
			query: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpGt,
					Left:  AttrRef{Path: "upstream.size"},
					Right: IntLiteral{Value: 1024},
				},
			},
		},
		{
			name:     "float literal",
			registry: registryWithAttributes(AttributeDefinition{Path: "user.score", Type: TypeFloat}),
			query: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpGte,
					Left:  AttrRef{Path: "user.score"},
					Right: FloatLiteral{Value: 98.5},
				},
			},
		},
		{
			name:     "boolean literal",
			registry: registryWithAttributes(AttributeDefinition{Path: "user.archived", Type: TypeBoolean}),
			query: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpEq,
					Left:  AttrRef{Path: "user.archived"},
					Right: BoolLiteral{Value: false},
				},
			},
		},
		{
			name:     "timestamp literal",
			registry: BuiltinRegistry(),
			query: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpGte,
					Left:  AttrRef{Path: "upstream.last_modified"},
					Right: TimestampLiteral{Value: mustTime("2026-06-26T00:00:00Z")},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := Bind(tt.query, tt.registry); err != nil {
				t.Fatalf("Bind returned error: %v", err)
			}
		})
	}
}

func TestBindIntegerLiteralWidensToFloat(t *testing.T) {
	_, err := Bind(Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op:    OpGt,
			Left:  AttrRef{Path: "user.score"},
			Right: IntLiteral{Value: 90},
		},
	}, registryWithAttributes(AttributeDefinition{Path: "user.score", Type: TypeFloat}))
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}
}

func TestBindNullOnlyValidWithIsNull(t *testing.T) {
	if _, err := Bind(Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &NullComparison{
			Left: AttrRef{Path: "user.owner"},
		},
	}, BuiltinRegistry()); err != nil {
		t.Fatalf("Bind IS NULL returned error: %v", err)
	}

	if _, err := Bind(Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &NullComparison{
			Left: AttrRef{Path: "user.owner"},
			Not:  true,
		},
	}, BuiltinRegistry()); err != nil {
		t.Fatalf("Bind IS NOT NULL returned error: %v", err)
	}

	if _, err := Bind(Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &Comparison{
			Op:    OpEq,
			Left:  AttrRef{Path: "user.owner"},
			Right: NullLiteral{},
		},
	}, BuiltinRegistry()); err == nil {
		t.Fatal("Bind accepted = NULL")
	}
}

func TestBindRejectsLiteralTypeMismatches(t *testing.T) {
	tests := []struct {
		name  string
		query Query
	}{
		{
			name: "string attribute compared with integer",
			query: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpEq,
					Left:  AttrRef{Path: "upstream.header.content_type"},
					Right: IntLiteral{Value: 10},
				},
			},
		},
		{
			name: "integer attribute compared with string",
			query: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpEq,
					Left:  AttrRef{Path: "upstream.size"},
					Right: StringLiteral{Value: "large"},
				},
			},
		},
		{
			name: "string attribute range comparison",
			query: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpGt,
					Left:  AttrRef{Path: "upstream.header.content_type"},
					Right: StringLiteral{Value: "image/jpeg"},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := Bind(tt.query, BuiltinRegistry()); err == nil {
				t.Fatal("Bind returned nil error")
			}
		})
	}
}

func TestBindValidOperatorTypeRules(t *testing.T) {
	tests := []struct {
		name     string
		registry Registry
		where    Expr
	}{
		{
			name:     "string equals string",
			registry: BuiltinRegistry(),
			where: Comparison{
				Op:    OpEq,
				Left:  AttrRef{Path: "upstream.header.content_type"},
				Right: StringLiteral{Value: "image/jpeg"},
			},
		},
		{
			name:     "string not equals string",
			registry: BuiltinRegistry(),
			where: Comparison{
				Op:    OpNeq,
				Left:  AttrRef{Path: "upstream.header.content_type"},
				Right: StringLiteral{Value: "image/png"},
			},
		},
		{
			name:     "string LIKE string",
			registry: BuiltinRegistry(),
			where: Comparison{
				Op:    OpLike,
				Left:  AttrRef{Path: "upstream.header.content_type"},
				Right: StringLiteral{Value: "image/%"},
			},
		},
		{
			name:     "string ILIKE string",
			registry: BuiltinRegistry(),
			where: Comparison{
				Op:    OpILike,
				Left:  AttrRef{Path: "upstream.header.content_type"},
				Right: StringLiteral{Value: "IMAGE/%"},
			},
		},
		{
			name:     "integer greater than integer",
			registry: BuiltinRegistry(),
			where: Comparison{
				Op:    OpGt,
				Left:  AttrRef{Path: "upstream.size"},
				Right: IntLiteral{Value: 1024},
			},
		},
		{
			name:     "integer BETWEEN integer bounds",
			registry: BuiltinRegistry(),
			where: BetweenComparison{
				Left:  AttrRef{Path: "upstream.size"},
				Lower: IntLiteral{Value: 1024},
				Upper: IntLiteral{Value: 4096},
			},
		},
		{
			name:     "timestamp greater than or equal timestamp",
			registry: BuiltinRegistry(),
			where: Comparison{
				Op:    OpGte,
				Left:  AttrRef{Path: "upstream.last_modified"},
				Right: TimestampLiteral{Value: mustTime("2026-06-26T00:00:00Z")},
			},
		},
		{
			name:     "boolean equals boolean",
			registry: registryWithAttributes(AttributeDefinition{Path: "user.archived", Type: TypeBoolean}),
			where: Comparison{
				Op:    OpEq,
				Left:  AttrRef{Path: "user.archived"},
				Right: BoolLiteral{Value: true},
			},
		},
		{
			name:     "attr IS NULL",
			registry: BuiltinRegistry(),
			where: NullComparison{
				Left: AttrRef{Path: "user.owner"},
			},
		},
		{
			name:     "attr IS NOT NULL",
			registry: BuiltinRegistry(),
			where: NullComparison{
				Left: AttrRef{Path: "user.owner"},
				Not:  true,
			},
		},
		{
			name:     "IN with compatible value types",
			registry: BuiltinRegistry(),
			where: InComparison{
				Left: AttrRef{Path: "upstream.size"},
				Values: []Expr{
					IntLiteral{Value: 1024},
					IntLiteral{Value: 4096},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := Bind(queryWithWhere(tt.where), tt.registry); err != nil {
				t.Fatalf("Bind returned error: %v", err)
			}
		})
	}
}

func TestBindInvalidOperatorTypeRules(t *testing.T) {
	tests := []struct {
		name     string
		registry Registry
		where    Expr
	}{
		{
			name:     "string greater than integer",
			registry: BuiltinRegistry(),
			where: Comparison{
				Op:    OpGt,
				Left:  AttrRef{Path: "upstream.header.content_type"},
				Right: IntLiteral{Value: 10},
			},
		},
		{
			name:     "string LIKE integer",
			registry: BuiltinRegistry(),
			where: Comparison{
				Op:    OpLike,
				Left:  AttrRef{Path: "upstream.header.content_type"},
				Right: IntLiteral{Value: 10},
			},
		},
		{
			name:     "integer LIKE string",
			registry: BuiltinRegistry(),
			where: Comparison{
				Op:    OpLike,
				Left:  AttrRef{Path: "upstream.size"},
				Right: StringLiteral{Value: "10%"},
			},
		},
		{
			name:     "timestamp LIKE string",
			registry: BuiltinRegistry(),
			where: Comparison{
				Op:    OpLike,
				Left:  AttrRef{Path: "upstream.last_modified"},
				Right: StringLiteral{Value: "2026%"},
			},
		},
		{
			name:     "boolean greater than boolean",
			registry: registryWithAttributes(AttributeDefinition{Path: "user.archived", Type: TypeBoolean}),
			where: Comparison{
				Op:    OpGt,
				Left:  AttrRef{Path: "user.archived"},
				Right: BoolLiteral{Value: false},
			},
		},
		{
			name:     "IN with mixed incompatible values",
			registry: BuiltinRegistry(),
			where: InComparison{
				Left: AttrRef{Path: "upstream.size"},
				Values: []Expr{
					IntLiteral{Value: 1024},
					StringLiteral{Value: "4096"},
				},
			},
		},
		{
			name:     "BETWEEN with mismatched bounds",
			registry: BuiltinRegistry(),
			where: BetweenComparison{
				Left:  AttrRef{Path: "upstream.size"},
				Lower: IntLiteral{Value: 1024},
				Upper: StringLiteral{Value: "4096"},
			},
		},
		{
			name:     "equals NULL",
			registry: BuiltinRegistry(),
			where: Comparison{
				Op:    OpEq,
				Left:  AttrRef{Path: "user.owner"},
				Right: NullLiteral{},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := Bind(queryWithWhere(tt.where), tt.registry); err == nil {
				t.Fatal("Bind returned nil error")
			}
		})
	}
}

func TestBindAndRecordsBothBranchDependencies(t *testing.T) {
	query := queryWithWhere(&BoolExpr{
		Op: BoolAnd,
		Terms: []Expr{
			Comparison{
				Op:    OpEq,
				Left:  AttrRef{Path: "upstream.header.content_type"},
				Right: StringLiteral{Value: "image/jpeg"},
			},
			Comparison{
				Op:    OpGt,
				Left:  AttrRef{Path: "upstream.size"},
				Right: IntLiteral{Value: 1024},
			},
		},
	})

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyAttribute, Name: "upstream.header.content_type", Type: TypeString},
			{Kind: DependencyAttribute, Name: "upstream.size", Type: TypeInteger},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindOrRecordsBothBranchDependencies(t *testing.T) {
	query := queryWithWhere(&BoolExpr{
		Op: BoolOr,
		Terms: []Expr{
			Comparison{
				Op:    OpEq,
				Left:  AttrRef{Path: "upstream.header.content_type"},
				Right: StringLiteral{Value: "image/jpeg"},
			},
			Comparison{
				Op:    OpGte,
				Left:  AttrRef{Path: "upstream.last_modified"},
				Right: TimestampLiteral{Value: mustTime("2026-06-26T00:00:00Z")},
			},
		},
	})

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyAttribute, Name: "upstream.header.content_type", Type: TypeString},
			{Kind: DependencyAttribute, Name: "upstream.last_modified", Type: TypeTimestamp},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindNotRecordsChildDependencies(t *testing.T) {
	query := queryWithWhere(NotExpr{
		Expr: Comparison{
			Op:    OpEq,
			Left:  AttrRef{Path: "upstream.header.content_type"},
			Right: StringLiteral{Value: "image/jpeg"},
		},
	})

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyAttribute, Name: "upstream.header.content_type", Type: TypeString},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindParenthesizedPrecedenceDoesNotChangeDependencies(t *testing.T) {
	query := queryWithWhere(&BoolExpr{
		Op: BoolOr,
		Terms: []Expr{
			Comparison{
				Op:    OpEq,
				Left:  AttrRef{Path: "upstream.header.content_type"},
				Right: StringLiteral{Value: "image/jpeg"},
			},
			&BoolExpr{
				Op: BoolAnd,
				Terms: []Expr{
					Comparison{
						Op:    OpGt,
						Left:  AttrRef{Path: "upstream.size"},
						Right: IntLiteral{Value: 1024},
					},
					Comparison{
						Op:    OpGte,
						Left:  AttrRef{Path: "upstream.last_modified"},
						Right: TimestampLiteral{Value: mustTime("2026-06-26T00:00:00Z")},
					},
				},
			},
		},
	})

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyAttribute, Name: "upstream.header.content_type", Type: TypeString},
			{Kind: DependencyAttribute, Name: "upstream.last_modified", Type: TypeTimestamp},
			{Kind: DependencyAttribute, Name: "upstream.size", Type: TypeInteger},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindDependencyOutputIncludesTargetFieldsAttributesAndTypes(t *testing.T) {
	query := queryWithWhere(&BoolExpr{
		Op: BoolAnd,
		Terms: []Expr{
			Comparison{
				Op:    OpEq,
				Left:  FieldRef{Name: "key"},
				Right: StringLiteral{Value: "photos/a.jpg"},
			},
			Comparison{
				Op:    OpGt,
				Left:  AttrRef{Path: "upstream.size"},
				Right: IntLiteral{Value: 1024},
			},
		},
	})

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyField, Name: "key", Type: TypeString},
			{Kind: DependencyAttribute, Name: "upstream.size", Type: TypeInteger},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindDependenciesAreStableSorted(t *testing.T) {
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &BoolExpr{
			Op: BoolAnd,
			Terms: []Expr{
				Comparison{
					Op:    OpGt,
					Left:  AttrRef{Path: "upstream.size"},
					Right: IntLiteral{Value: 1024},
				},
				Comparison{
					Op:    OpEq,
					Left:  FieldRef{Name: "key"},
					Right: StringLiteral{Value: "photos/a.jpg"},
				},
				Comparison{
					Op:    OpEq,
					Left:  AttrRef{Path: "upstream.header.content_type"},
					Right: StringLiteral{Value: "image/jpeg"},
				},
			},
		},
		OrderBy: []OrderExpr{
			{
				Expr:      FieldRef{Name: "updated_at"},
				Direction: SortDesc,
			},
		},
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyField, Name: "key", Type: TypeString},
			{Kind: DependencyField, Name: "updated_at", Type: TypeTimestamp},
			{Kind: DependencyAttribute, Name: "upstream.header.content_type", Type: TypeString},
			{Kind: DependencyAttribute, Name: "upstream.size", Type: TypeInteger},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindDependenciesAreDedupedAcrossDependencyKinds(t *testing.T) {
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where: &BoolExpr{
			Op: BoolAnd,
			Terms: []Expr{
				Comparison{
					Op:    OpEq,
					Left:  FieldRef{Name: "key"},
					Right: StringLiteral{Value: "photos/a.jpg"},
				},
				Comparison{
					Op:    OpNeq,
					Left:  FieldRef{Name: "key"},
					Right: StringLiteral{Value: "photos/b.jpg"},
				},
				Comparison{
					Op:    OpGt,
					Left:  AttrRef{Path: "upstream.size"},
					Right: IntLiteral{Value: 1024},
				},
				Comparison{
					Op:    OpLt,
					Left:  AttrRef{Path: "upstream.size"},
					Right: IntLiteral{Value: 4096},
				},
			},
		},
		OrderBy: []OrderExpr{
			{
				Expr:      FieldRef{Name: "key"},
				Direction: SortAsc,
			},
			{
				Expr:      AttrRef{Path: "upstream.size"},
				Direction: SortDesc,
			},
		},
	}

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyField, Name: "key", Type: TypeString},
			{Kind: DependencyAttribute, Name: "upstream.size", Type: TypeInteger},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindRegistryTypeChangeChangesDependencyType(t *testing.T) {
	query := Query{
		Version: VersionV1,
		From:    TargetObjects,
		OrderBy: []OrderExpr{
			{
				Expr:      AttrRef{Path: "user.score"},
				Direction: SortDesc,
			},
		},
	}

	integerBound, err := Bind(query, registryWithAttributes(AttributeDefinition{Path: "user.score", Type: TypeInteger}))
	if err != nil {
		t.Fatalf("Bind with integer registry returned error: %v", err)
	}
	floatBound, err := Bind(query, registryWithAttributes(AttributeDefinition{Path: "user.score", Type: TypeFloat}))
	if err != nil {
		t.Fatalf("Bind with float registry returned error: %v", err)
	}

	assertBoundQueryEqual(t, integerBound, BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyAttribute, Name: "user.score", Type: TypeInteger},
		},
	})
	assertBoundQueryEqual(t, floatBound, BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyAttribute, Name: "user.score", Type: TypeFloat},
		},
	})
}

func TestBindNestedBooleanTypeErrorBubblesWithContext(t *testing.T) {
	_, err := Bind(queryWithWhere(&BoolExpr{
		Op: BoolOr,
		Terms: []Expr{
			Comparison{
				Op:    OpEq,
				Left:  AttrRef{Path: "upstream.header.content_type"},
				Right: StringLiteral{Value: "image/jpeg"},
			},
			NotExpr{
				Expr: Comparison{
					Op:    OpGt,
					Left:  AttrRef{Path: "upstream.header.content_type"},
					Right: IntLiteral{Value: 10},
				},
			},
		},
	}), BuiltinRegistry())
	if err == nil {
		t.Fatal("Bind returned nil error")
	}

	got := err.Error()
	for _, want := range []string{"or term 2", "not expression", "cannot apply gt"} {
		if !strings.Contains(got, want) {
			t.Fatalf("error %q does not contain %q", got, want)
		}
	}
}

func TestBindRecordsRelationPredicateDependency(t *testing.T) {
	query := queryWithWhere(&RelationPredicate{
		Type:      "duplicate",
		Direction: RelationAny,
	})

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyRelation, Name: "duplicate"},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindRecordsRelationPredicateDependenciesInBooleanLogic(t *testing.T) {
	query := queryWithWhere(&BoolExpr{
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
	})

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyRelation, Name: "duplicate"},
			{Kind: DependencyRelation, Name: "thumbnail_of"},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindRecordsBucketPredicateDependency(t *testing.T) {
	query := queryWithWhere(&BucketPredicate{
		Name: "production",
	})

	bound, err := Bind(query, BuiltinRegistry())
	if err != nil {
		t.Fatalf("Bind returned error: %v", err)
	}

	want := BoundQuery{
		Query: query,
		Dependencies: []Dependency{
			{Kind: DependencyTarget, Name: "objects"},
			{Kind: DependencyBucket, Name: "production"},
		},
	}
	assertBoundQueryEqual(t, bound, want)
}

func TestBindRejectsRelationPredicateOnRelationsTarget(t *testing.T) {
	_, err := Bind(Query{
		Version: VersionV1,
		From:    TargetRelations,
		Where: &RelationPredicate{
			Type:      "duplicate",
			Direction: RelationAny,
		},
	}, BuiltinRegistry())
	if err == nil {
		t.Fatal("Bind returned nil error")
	}
}

func TestBindRejectsFieldsForWrongTarget(t *testing.T) {
	tests := []struct {
		name  string
		query Query
	}{
		{
			name: "object field on relations",
			query: Query{
				Version: VersionV1,
				From:    TargetRelations,
				Where: &Comparison{
					Op:    OpEq,
					Left:  FieldRef{Name: "key"},
					Right: StringLiteral{Value: "photos/a.jpg"},
				},
			},
		},
		{
			name: "relation field on objects",
			query: Query{
				Version: VersionV1,
				From:    TargetObjects,
				Where: &Comparison{
					Op:    OpEq,
					Left:  FieldRef{Name: "relation_type"},
					Right: StringLiteral{Value: "duplicate"},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := Bind(tt.query, BuiltinRegistry()); err == nil {
				t.Fatal("Bind returned nil error")
			}
		})
	}
}

func TestBindRejectsTargetSpecificFieldsInOrderBy(t *testing.T) {
	_, err := Bind(Query{
		Version: VersionV1,
		From:    TargetRelations,
		OrderBy: []OrderExpr{
			{
				Expr:      FieldRef{Name: "key"},
				Direction: SortAsc,
			},
		},
	}, BuiltinRegistry())
	if err == nil {
		t.Fatal("Bind returned nil error")
	}
}

func assertBoundQueryEqual(t *testing.T, got BoundQuery, want BoundQuery) {
	t.Helper()

	if diff := got.Diff(want); diff != "" {
		t.Fatalf("bound query mismatch (-got +want):\n%s", diff)
	}
}

func registryWithAttributes(attributes ...AttributeDefinition) Registry {
	return NewStaticRegistry(BuiltinTargetDefinitions(), attributes)
}

func queryWithWhere(where Expr) Query {
	return Query{
		Version: VersionV1,
		From:    TargetObjects,
		Where:   where,
	}
}

func mustTime(value string) time.Time {
	parsed, err := time.Parse(time.RFC3339, value)
	if err != nil {
		panic(err)
	}
	return parsed
}

func literalForType(typ ValueType) Expr {
	switch typ {
	case TypeString:
		return StringLiteral{Value: "value"}
	case TypeInteger:
		return IntLiteral{Value: 1}
	case TypeFloat:
		return FloatLiteral{Value: 1.5}
	case TypeBoolean:
		return BoolLiteral{Value: true}
	case TypeTimestamp:
		return TimestampLiteral{Value: mustTime("2026-06-26T00:00:00Z")}
	default:
		return NullLiteral{}
	}
}
