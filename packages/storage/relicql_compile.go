package storage

import (
	"fmt"
	"strings"
	"time"

	"github.com/ekkuleivonen/relic/packages/search"
)

type SearchScope struct {
	BucketID string
}

type CompiledQuery struct {
	SQL  string
	Args []any
}

const objectsSearchSelectSQL = `
SELECT
	objects.id,
	objects.bucket_id,
	objects.key,
	objects.attributes,
	objects.attribute_provenance,
	objects.created_at,
	objects.updated_at
FROM objects`

func CompileObjectsSearch(bound search.BoundQuery, scope SearchScope) (CompiledQuery, error) {
	if bound.Query.From != search.TargetObjects {
		return CompiledQuery{}, fmt.Errorf("compile RelicQL: unsupported target %q", bound.Query.From)
	}

	ctx := newCompileContext(bound)

	whereParts := []string{}
	if scope.BucketID != "" {
		whereParts = append(whereParts, fmt.Sprintf("objects.bucket_id = %s", ctx.addArg(scope.BucketID)))
	}
	if bound.Query.Where != nil {
		whereSQL, err := ctx.compileExpr(bound.Query.Where)
		if err != nil {
			return CompiledQuery{}, err
		}
		whereParts = append(whereParts, whereSQL)
	}

	sqlBuilder := strings.Builder{}
	sqlBuilder.WriteString(strings.TrimSpace(objectsSearchSelectSQL))
	if len(whereParts) > 0 {
		sqlBuilder.WriteString("\nWHERE ")
		sqlBuilder.WriteString(strings.Join(whereParts, " AND "))
	}

	if len(bound.Query.OrderBy) > 0 {
		orderTerms := make([]string, 0, len(bound.Query.OrderBy))
		for _, order := range bound.Query.OrderBy {
			termSQL, err := ctx.compileOrderExpr(order)
			if err != nil {
				return CompiledQuery{}, err
			}
			orderTerms = append(orderTerms, termSQL)
		}
		sqlBuilder.WriteString("\nORDER BY ")
		sqlBuilder.WriteString(strings.Join(orderTerms, ", "))
	}

	if bound.Query.Limit != nil {
		sqlBuilder.WriteString("\nLIMIT ")
		sqlBuilder.WriteString(ctx.addArg(int64(*bound.Query.Limit)))
	}
	if bound.Query.Offset != nil {
		sqlBuilder.WriteString("\nOFFSET ")
		sqlBuilder.WriteString(ctx.addArg(int64(*bound.Query.Offset)))
	}

	return CompiledQuery{
		SQL:  sqlBuilder.String(),
		Args: ctx.args,
	}, nil
}

type compileContext struct {
	target    search.Target
	attrTypes map[string]search.ValueType
	args      []any
}

func newCompileContext(bound search.BoundQuery) *compileContext {
	return &compileContext{
		target:    bound.Query.From,
		attrTypes: attributeTypesFromDependencies(bound.Dependencies),
		args:      []any{},
	}
}

func attributeTypesFromDependencies(dependencies []search.Dependency) map[string]search.ValueType {
	types := map[string]search.ValueType{}
	for _, dependency := range dependencies {
		if dependency.Kind != search.DependencyAttribute {
			continue
		}
		types[dependency.Name] = dependency.Type
	}

	return types
}

func (c *compileContext) addArg(value any) string {
	c.args = append(c.args, value)
	return fmt.Sprintf("$%d", len(c.args))
}

func (c *compileContext) compileOrderExpr(order search.OrderExpr) (string, error) {
	exprSQL, err := c.compileValueExpr(order.Expr)
	if err != nil {
		return "", err
	}

	direction := "ASC"
	if order.Direction == search.SortDesc {
		direction = "DESC"
	}

	return exprSQL + " " + direction, nil
}

func (c *compileContext) compileExpr(expr search.Expr) (string, error) {
	return c.compileExprNested(expr, false)
}

func (c *compileContext) compileExprNested(expr search.Expr, nested bool) (string, error) {
	switch typed := expr.(type) {
	case *search.BoolExpr:
		return c.compileBoolExpr(*typed, nested)
	case *search.NotExpr:
		return c.compileNotExpr(*typed)
	case search.NotExpr:
		return c.compileNotExpr(typed)
	case *search.Comparison:
		return c.compileComparison(*typed)
	case search.Comparison:
		return c.compileComparison(typed)
	case *search.InComparison:
		return c.compileInComparison(*typed)
	case search.InComparison:
		return c.compileInComparison(typed)
	case *search.BetweenComparison:
		return c.compileBetweenComparison(*typed)
	case search.BetweenComparison:
		return c.compileBetweenComparison(typed)
	case *search.NullComparison:
		return c.compileNullComparison(*typed)
	case search.NullComparison:
		return c.compileNullComparison(typed)
	case *search.RelationPredicate:
		return c.compileRelationPredicate(*typed)
	case search.RelationPredicate:
		return c.compileRelationPredicate(typed)
	default:
		return "", fmt.Errorf("compile RelicQL: unsupported expression %T", expr)
	}
}

func (c *compileContext) compileBoolExpr(expr search.BoolExpr, nested bool) (string, error) {
	if len(expr.Terms) == 0 {
		return "", fmt.Errorf("compile RelicQL: boolean expression has no terms")
	}

	joiner := " AND "
	if expr.Op == search.BoolOr {
		joiner = " OR "
	}

	terms := make([]string, 0, len(expr.Terms))
	for _, term := range expr.Terms {
		termSQL, err := c.compileExprNested(term, true)
		if err != nil {
			return "", err
		}
		terms = append(terms, termSQL)
	}

	if len(terms) == 1 {
		return terms[0], nil
	}

	joined := strings.Join(terms, joiner)
	if nested {
		return "(" + joined + ")", nil
	}

	return joined, nil
}

func (c *compileContext) compileNotExpr(expr search.NotExpr) (string, error) {
	innerSQL, err := c.compileExprNested(expr.Expr, true)
	if err != nil {
		return "", err
	}

	return "NOT (" + innerSQL + ")", nil
}

func (c *compileContext) compileComparison(comparison search.Comparison) (string, error) {
	leftSQL, err := c.compileScalarExpr(comparison.Left)
	if err != nil {
		return "", err
	}
	rightSQL, err := c.compileScalarExpr(comparison.Right)
	if err != nil {
		return "", err
	}

	operator, err := comparisonOperator(comparison.Op)
	if err != nil {
		return "", err
	}

	return leftSQL + " " + operator + " " + rightSQL, nil
}

func (c *compileContext) compileInComparison(comparison search.InComparison) (string, error) {
	leftSQL, err := c.compileValueExpr(comparison.Left)
	if err != nil {
		return "", err
	}
	if len(comparison.Values) == 0 {
		return "", fmt.Errorf("compile RelicQL: IN requires at least one value")
	}

	valueArgs := make([]string, 0, len(comparison.Values))
	for _, value := range comparison.Values {
		arg, err := c.compileScalarExpr(value)
		if err != nil {
			return "", err
		}
		valueArgs = append(valueArgs, arg)
	}

	return leftSQL + " IN (" + strings.Join(valueArgs, ", ") + ")", nil
}

func (c *compileContext) compileBetweenComparison(comparison search.BetweenComparison) (string, error) {
	leftSQL, err := c.compileValueExpr(comparison.Left)
	if err != nil {
		return "", err
	}
	lowerSQL, err := c.compileScalarExpr(comparison.Lower)
	if err != nil {
		return "", err
	}
	upperSQL, err := c.compileScalarExpr(comparison.Upper)
	if err != nil {
		return "", err
	}

	return leftSQL + " BETWEEN " + lowerSQL + " AND " + upperSQL, nil
}

func (c *compileContext) compileNullComparison(comparison search.NullComparison) (string, error) {
	leftSQL, err := c.compileValueExpr(comparison.Left)
	if err != nil {
		return "", err
	}
	if comparison.Not {
		return leftSQL + " IS NOT NULL", nil
	}

	return leftSQL + " IS NULL", nil
}

func (c *compileContext) compileRelationPredicate(predicate search.RelationPredicate) (string, error) {
	relationTypeArg := c.addArg(predicate.Type)

	objectMatchSQL, err := relationObjectMatchSQL(predicate.Direction)
	if err != nil {
		return "", err
	}

	return fmt.Sprintf(`EXISTS (
	SELECT 1
	FROM relations r
	WHERE %s
		AND r.relation_type = %s
)`, objectMatchSQL, relationTypeArg), nil
}

func relationObjectMatchSQL(direction search.RelationDirection) (string, error) {
	switch direction {
	case search.RelationOut:
		return "r.source_object_id = objects.id", nil
	case search.RelationIn:
		return "r.target_object_id = objects.id", nil
	case search.RelationAny:
		return "(r.source_object_id = objects.id OR r.target_object_id = objects.id)", nil
	default:
		return "", fmt.Errorf("compile RelicQL: unsupported relation direction %q", direction)
	}
}

func (c *compileContext) compileScalarExpr(expr search.Expr) (string, error) {
	switch typed := expr.(type) {
	case search.NowExpr:
		return "now()", nil
	case search.IntervalLiteral:
		return search.FormatIntervalSQL(typed.Value)
	case search.ArithmeticExpr:
		return c.compileArithmeticExpr(typed)
	case search.CastExpr:
		if _, ok := typed.Expr.(search.AttrRef); ok {
			return c.compileCastExpr(typed)
		}
		return c.compileLiteralArg(expr)
	}

	switch expr.(type) {
	case search.FieldRef, search.AttrRef:
		return c.compileValueExpr(expr)
	default:
		return c.compileLiteralArg(expr)
	}
}

func (c *compileContext) compileArithmeticExpr(expr search.ArithmeticExpr) (string, error) {
	leftSQL, err := c.compileScalarExpr(expr.Left)
	if err != nil {
		return "", err
	}
	rightSQL, err := c.compileScalarExpr(expr.Right)
	if err != nil {
		return "", err
	}

	operator := "+"
	if expr.Op == search.ArithSub {
		operator = "-"
	}

	return "(" + leftSQL + " " + operator + " " + rightSQL + ")", nil
}

func (c *compileContext) compileValueExpr(expr search.Expr) (string, error) {
	switch typed := expr.(type) {
	case search.FieldRef:
		return search.FieldSQLColumn(c.target, typed.Name)
	case search.AttrRef:
		return c.compileAttrRef(typed)
	case search.CastExpr:
		return c.compileCastExpr(typed)
	default:
		return "", fmt.Errorf("compile RelicQL: expected field or attribute reference, got %T", expr)
	}
}

func (c *compileContext) compileCastExpr(cast search.CastExpr) (string, error) {
	switch inner := cast.Expr.(type) {
	case search.AttrRef:
		return attributeSQLExpr(inner.Path, cast.Type)
	case search.StringLiteral:
		if cast.Type != search.TypeTimestamp {
			return "", fmt.Errorf("compile RelicQL: unsupported cast from string to %q", cast.Type)
		}
		value, err := parseTimestampText(inner.Value)
		if err != nil {
			return "", err
		}
		return c.addArg(value), nil
	default:
		return "", fmt.Errorf("compile RelicQL: unsupported cast operand %T", cast.Expr)
	}
}

func (c *compileContext) compileAttrRef(ref search.AttrRef) (string, error) {
	typ, ok := c.attrTypes[ref.Path]
	if !ok {
		typ = search.TypeUnknown
	}

	return attributeSQLExpr(ref.Path, typ)
}

func (c *compileContext) compileLiteralArg(expr search.Expr) (string, error) {
	value, err := literalValue(expr)
	if err != nil {
		return "", err
	}

	return c.addArg(value), nil
}

func literalValue(expr search.Expr) (any, error) {
	if cast, ok := expr.(search.CastExpr); ok {
		if stringLiteral, ok := cast.Expr.(search.StringLiteral); ok && cast.Type == search.TypeTimestamp {
			return parseTimestampText(stringLiteral.Value)
		}
	}

	switch typed := expr.(type) {
	case search.StringLiteral:
		return typed.Value, nil
	case search.IntLiteral:
		return typed.Value, nil
	case search.FloatLiteral:
		return typed.Value, nil
	case search.BoolLiteral:
		return typed.Value, nil
	case search.TimestampLiteral:
		return typed.Value, nil
	default:
		return nil, fmt.Errorf("compile RelicQL: unsupported literal %T", expr)
	}
}

func parseTimestampText(value string) (time.Time, error) {
	if parsed, err := time.Parse("2006-01-02", value); err == nil {
		return parsed.UTC(), nil
	}
	parsed, err := time.Parse(time.RFC3339, value)
	if err != nil {
		return time.Time{}, fmt.Errorf("compile RelicQL: invalid timestamp value %q", value)
	}

	return parsed.UTC(), nil
}

func comparisonOperator(op search.ComparisonOp) (string, error) {
	switch op {
	case search.OpEq:
		return "=", nil
	case search.OpNeq:
		return "<>", nil
	case search.OpLt:
		return "<", nil
	case search.OpLte:
		return "<=", nil
	case search.OpGt:
		return ">", nil
	case search.OpGte:
		return ">=", nil
	case search.OpLike:
		return "LIKE", nil
	case search.OpILike:
		return "ILIKE", nil
	default:
		return "", fmt.Errorf("compile RelicQL: unsupported comparison operator %q", op)
	}
}

func attributeSQLExpr(path string, typ search.ValueType) (string, error) {
	textPath, err := jsonbTextPathLiteral(path)
	if err != nil {
		return "", err
	}

	base := fmt.Sprintf("objects.attributes #>> %s", textPath)
	switch typ {
	case search.TypeString, search.TypeUnknown:
		return base, nil
	case search.TypeInteger:
		return "(" + base + ")::bigint", nil
	case search.TypeFloat:
		return "(" + base + ")::double precision", nil
	case search.TypeBoolean:
		return "(" + base + ")::boolean", nil
	case search.TypeTimestamp:
		return "(" + base + ")::timestamptz", nil
	default:
		return "", fmt.Errorf("compile RelicQL: unsupported attribute type %q for path %q", typ, path)
	}
}

func jsonbTextPathLiteral(path string) (string, error) {
	parts := splitAttributePath(path)
	jsonPath, err := NewJSONBPath(parts...)
	if err != nil {
		return "", fmt.Errorf("compile RelicQL attribute path %q: %w", path, err)
	}

	segments := make([]string, 0, len(jsonPath))
	for _, segment := range jsonPath {
		segments = append(segments, segment)
	}

	return "'{" + strings.Join(segments, ",") + "}'", nil
}
