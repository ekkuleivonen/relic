package search

import (
	"fmt"
	"reflect"
	"sort"
)

type DependencyKind string

const (
	DependencyTarget    DependencyKind = "target"
	DependencyField     DependencyKind = "field"
	DependencyAttribute DependencyKind = "attribute"
	DependencyRelation  DependencyKind = "relation"
)

type Dependency struct {
	Kind DependencyKind
	Name string
	Type ValueType
}

type BoundQuery struct {
	Query        Query
	Dependencies []Dependency
}

func (q BoundQuery) Diff(want BoundQuery) string {
	if reflect.DeepEqual(q, want) {
		return ""
	}

	return fmt.Sprintf("- %#v\n+ %#v", q, want)
}

func Bind(query Query, registry Registry) (BoundQuery, error) {
	if registry == nil {
		return BoundQuery{}, fmt.Errorf("bind RelicQL: registry is required")
	}
	if _, ok := registry.ResolveTarget(query.From); !ok {
		return BoundQuery{}, fmt.Errorf("bind RelicQL: unsupported target %q", query.From)
	}

	binder := queryBinder{
		query:        query,
		registry:     registry,
		dependencies: []Dependency{{Kind: DependencyTarget, Name: string(query.From)}},
	}

	if query.Where != nil {
		if err := binder.bindExpr(query.Where); err != nil {
			return BoundQuery{}, err
		}
	}
	for _, order := range query.OrderBy {
		if err := binder.bindExpr(order.Expr); err != nil {
			return BoundQuery{}, err
		}
	}
	sortDependencies(binder.dependencies)

	return BoundQuery{
		Query:        query,
		Dependencies: binder.dependencies,
	}, nil
}

type queryBinder struct {
	query        Query
	registry     Registry
	dependencies []Dependency
}

func (b *queryBinder) bindExpr(expr Expr) error {
	switch typed := expr.(type) {
	case *BoolExpr:
		for index, term := range typed.Terms {
			if err := b.bindExpr(term); err != nil {
				return fmt.Errorf("bind RelicQL: %s term %d: %w", typed.Op, index+1, err)
			}
		}
	case *NotExpr:
		if err := b.bindExpr(typed.Expr); err != nil {
			return fmt.Errorf("bind RelicQL: not expression: %w", err)
		}
	case NotExpr:
		if err := b.bindExpr(typed.Expr); err != nil {
			return fmt.Errorf("bind RelicQL: not expression: %w", err)
		}
	case *Comparison:
		return b.bindComparison(*typed)
	case Comparison:
		return b.bindComparison(typed)
	case *InComparison:
		return b.bindInComparison(*typed)
	case InComparison:
		return b.bindInComparison(typed)
	case *BetweenComparison:
		return b.bindBetweenComparison(*typed)
	case BetweenComparison:
		return b.bindBetweenComparison(typed)
	case *NullComparison:
		return b.bindExpr(typed.Left)
	case NullComparison:
		return b.bindExpr(typed.Left)
	case *RelationPredicate:
		return b.bindRelationPredicate(*typed)
	case RelationPredicate:
		return b.bindRelationPredicate(typed)
	case FieldRef:
		return b.bindField(typed)
	case AttrRef:
		return b.bindAttribute(typed)
	case StringLiteral, IntLiteral, FloatLiteral, BoolLiteral, TimestampLiteral, NullLiteral:
		return nil
	default:
		return fmt.Errorf("bind RelicQL: unsupported expression %T", expr)
	}

	return nil
}

func (b *queryBinder) bindField(field FieldRef) error {
	definition, ok := b.registry.ResolveField(b.query.From, field.Name)
	if !ok {
		return fmt.Errorf("bind RelicQL: field %q is not available on target %q", field.Name, b.query.From)
	}

	b.addDependency(Dependency{
		Kind: DependencyField,
		Name: field.Name,
		Type: definition.Type,
	})
	return nil
}

func (b *queryBinder) bindComparison(comparison Comparison) error {
	leftType, err := b.exprType(comparison.Left)
	if err != nil {
		return err
	}
	rightType, err := b.exprType(comparison.Right)
	if err != nil {
		return err
	}

	if !comparisonTypesCompatible(comparison.Op, leftType, rightType) {
		return fmt.Errorf("bind RelicQL: cannot apply %s to %s and %s", comparison.Op, leftType, rightType)
	}

	return nil
}

func (b *queryBinder) bindInComparison(comparison InComparison) error {
	leftType, err := b.exprType(comparison.Left)
	if err != nil {
		return err
	}

	for _, value := range comparison.Values {
		valueType, err := b.exprType(value)
		if err != nil {
			return err
		}
		if !comparisonTypesCompatible(OpEq, leftType, valueType) {
			return fmt.Errorf("bind RelicQL: cannot apply in to %s and %s", leftType, valueType)
		}
	}

	return nil
}

func (b *queryBinder) bindBetweenComparison(comparison BetweenComparison) error {
	leftType, err := b.exprType(comparison.Left)
	if err != nil {
		return err
	}
	lowerType, err := b.exprType(comparison.Lower)
	if err != nil {
		return err
	}
	upperType, err := b.exprType(comparison.Upper)
	if err != nil {
		return err
	}

	if !comparisonTypesCompatible(OpGte, leftType, lowerType) {
		return fmt.Errorf("bind RelicQL: cannot apply between to %s and %s lower bound", leftType, lowerType)
	}
	if !comparisonTypesCompatible(OpLte, leftType, upperType) {
		return fmt.Errorf("bind RelicQL: cannot apply between to %s and %s upper bound", leftType, upperType)
	}
	if !sameOrNumericTypes(lowerType, upperType) {
		return fmt.Errorf("bind RelicQL: between bounds must have compatible types, got %s and %s", lowerType, upperType)
	}

	return nil
}

func (b *queryBinder) exprType(expr Expr) (ValueType, error) {
	switch typed := expr.(type) {
	case FieldRef:
		definition, ok := b.registry.ResolveField(b.query.From, typed.Name)
		if !ok {
			return "", fmt.Errorf("bind RelicQL: field %q is not available on target %q", typed.Name, b.query.From)
		}
		b.addDependency(Dependency{
			Kind: DependencyField,
			Name: typed.Name,
			Type: definition.Type,
		})
		return definition.Type, nil
	case AttrRef:
		definition, ok := b.registry.ResolveAttribute(typed.Path)
		if !ok {
			definition = AttributeDefinition{
				Path: typed.Path,
				Type: TypeUnknown,
			}
		}
		b.addDependency(Dependency{
			Kind: DependencyAttribute,
			Name: typed.Path,
			Type: definition.Type,
		})
		return definition.Type, nil
	case StringLiteral:
		return TypeString, nil
	case IntLiteral:
		return TypeInteger, nil
	case FloatLiteral:
		return TypeFloat, nil
	case BoolLiteral:
		return TypeBoolean, nil
	case TimestampLiteral:
		return TypeTimestamp, nil
	case NullLiteral:
		return TypeNull, nil
	default:
		if err := b.bindExpr(expr); err != nil {
			return "", err
		}
		return TypeUnknown, nil
	}
}

func comparisonTypesCompatible(op ComparisonOp, left ValueType, right ValueType) bool {
	if left == TypeNull || right == TypeNull {
		return false
	}
	if left == TypeUnknown || right == TypeUnknown {
		return op == OpEq || op == OpNeq || op == OpLike || op == OpILike
	}

	switch op {
	case OpEq, OpNeq:
		return sameOrNumericTypes(left, right)
	case OpLt, OpLte, OpGt, OpGte:
		return bothNumericTypes(left, right) || (left == TypeTimestamp && right == TypeTimestamp)
	case OpLike, OpILike:
		return left == TypeString && right == TypeString
	default:
		return false
	}
}

func sameOrNumericTypes(left ValueType, right ValueType) bool {
	if left == right {
		return true
	}
	return bothNumericTypes(left, right)
}

func bothNumericTypes(left ValueType, right ValueType) bool {
	return (left == TypeInteger || left == TypeFloat) && (right == TypeInteger || right == TypeFloat)
}

func (b *queryBinder) bindRelationPredicate(predicate RelationPredicate) error {
	if b.query.From != TargetObjects {
		return fmt.Errorf("bind RelicQL: has_relation is only supported on target %q", b.query.From)
	}

	b.addDependency(Dependency{
		Kind: DependencyRelation,
		Name: predicate.Type,
	})
	return nil
}

func (b *queryBinder) bindAttribute(attribute AttrRef) error {
	definition, ok := b.registry.ResolveAttribute(attribute.Path)
	if !ok {
		definition = AttributeDefinition{
			Path: attribute.Path,
			Type: TypeUnknown,
		}
	}

	b.addDependency(Dependency{
		Kind: DependencyAttribute,
		Name: attribute.Path,
		Type: definition.Type,
	})
	return nil
}

func (b *queryBinder) addDependency(dependency Dependency) {
	for _, existing := range b.dependencies {
		if existing.Kind == dependency.Kind && existing.Name == dependency.Name {
			return
		}
	}

	b.dependencies = append(b.dependencies, dependency)
}

func sortDependencies(dependencies []Dependency) {
	sort.SliceStable(dependencies, func(i int, j int) bool {
		left := dependencies[i]
		right := dependencies[j]

		if left.Kind != right.Kind {
			return dependencyKindRank(left.Kind) < dependencyKindRank(right.Kind)
		}
		if left.Name != right.Name {
			return left.Name < right.Name
		}
		return left.Type < right.Type
	})
}

func dependencyKindRank(kind DependencyKind) int {
	switch kind {
	case DependencyTarget:
		return 0
	case DependencyField:
		return 1
	case DependencyAttribute:
		return 2
	case DependencyRelation:
		return 3
	default:
		return 99
	}
}
