package search

import (
	"fmt"
	"reflect"
	"time"
)

const VersionV1 = "relicql.v1"

type Target string

const (
	TargetObjects   Target = "objects"
	TargetRelations Target = "relations"
)

type Query struct {
	Version string
	From    Target
	Where   Expr
	OrderBy []OrderExpr
	Limit   *int
	Offset  *int
}

func (q Query) Diff(want Query) string {
	if reflect.DeepEqual(q, want) {
		return ""
	}

	return fmt.Sprintf("- %#v\n+ %#v", q, want)
}

type Expr interface {
	exprNode()
}

type BoolOp string

const (
	BoolAnd BoolOp = "and"
	BoolOr  BoolOp = "or"
)

type BoolExpr struct {
	Op    BoolOp
	Terms []Expr
}

func (*BoolExpr) exprNode() {}

type NotExpr struct {
	Expr Expr
}

func (NotExpr) exprNode() {}

type ComparisonOp string

const (
	OpEq    ComparisonOp = "eq"
	OpNeq   ComparisonOp = "neq"
	OpLt    ComparisonOp = "lt"
	OpLte   ComparisonOp = "lte"
	OpGt    ComparisonOp = "gt"
	OpGte   ComparisonOp = "gte"
	OpLike  ComparisonOp = "like"
	OpILike ComparisonOp = "ilike"
)

type Comparison struct {
	Op    ComparisonOp
	Left  Expr
	Right Expr
}

func (Comparison) exprNode() {}

type InComparison struct {
	Left   Expr
	Values []Expr
}

func (InComparison) exprNode() {}

type BetweenComparison struct {
	Left  Expr
	Lower Expr
	Upper Expr
}

func (BetweenComparison) exprNode() {}

type NullComparison struct {
	Left Expr
	Not  bool
}

func (NullComparison) exprNode() {}

type RelationDirection string

const (
	RelationAny RelationDirection = "any"
	RelationOut RelationDirection = "out"
	RelationIn  RelationDirection = "in"
)

type RelationPredicate struct {
	Type      string
	Direction RelationDirection
}

func (RelationPredicate) exprNode() {}

type FieldRef struct {
	Name string
}

func (FieldRef) exprNode() {}

type AttrRef struct {
	Path string
}

func (AttrRef) exprNode() {}

type CastExpr struct {
	Expr Expr
	Type ValueType
}

func (CastExpr) exprNode() {}

type StringLiteral struct {
	Value string
}

func (StringLiteral) exprNode() {}

type IntLiteral struct {
	Value int64
}

func (IntLiteral) exprNode() {}

type FloatLiteral struct {
	Value float64
}

func (FloatLiteral) exprNode() {}

type BoolLiteral struct {
	Value bool
}

func (BoolLiteral) exprNode() {}

type TimestampLiteral struct {
	Value time.Time
}

func (TimestampLiteral) exprNode() {}

type NowExpr struct{}

func (NowExpr) exprNode() {}

type IntervalLiteral struct {
	Value string
}

func (IntervalLiteral) exprNode() {}

type ArithmeticOp string

const (
	ArithAdd ArithmeticOp = "add"
	ArithSub ArithmeticOp = "sub"
)

type ArithmeticExpr struct {
	Op    ArithmeticOp
	Left  Expr
	Right Expr
}

func (ArithmeticExpr) exprNode() {}

type NullLiteral struct{}

func (NullLiteral) exprNode() {}

type SortDirection string

const (
	SortAsc  SortDirection = "asc"
	SortDesc SortDirection = "desc"
)

type OrderExpr struct {
	Expr      Expr
	Direction SortDirection
}
