package search

import (
	"encoding/json"
	"fmt"
	"time"
)

type queryDocument struct {
	Version string           `json:"version"`
	From    string           `json:"from"`
	Where   json.RawMessage  `json:"where,omitempty"`
	OrderBy []orderDocument  `json:"order_by,omitempty"`
	Limit   *int             `json:"limit,omitempty"`
	Offset  *int             `json:"offset,omitempty"`
}

type orderDocument struct {
	Expr      json.RawMessage `json:"expr"`
	Direction string          `json:"direction,omitempty"`
}

func MarshalQuery(q Query) ([]byte, error) {
	doc := queryDocument{
		Version: q.Version,
		From:    string(q.From),
		Limit:   q.Limit,
		Offset:  q.Offset,
	}

	if q.Where != nil {
		where, err := marshalExpr(q.Where)
		if err != nil {
			return nil, fmt.Errorf("marshal query where: %w", err)
		}
		doc.Where = where
	}

	if len(q.OrderBy) > 0 {
		doc.OrderBy = make([]orderDocument, 0, len(q.OrderBy))
		for _, order := range q.OrderBy {
			expr, err := marshalExpr(order.Expr)
			if err != nil {
				return nil, fmt.Errorf("marshal order expr: %w", err)
			}
			doc.OrderBy = append(doc.OrderBy, orderDocument{
				Expr:      expr,
				Direction: string(order.Direction),
			})
		}
	}

	data, err := json.Marshal(doc)
	if err != nil {
		return nil, fmt.Errorf("marshal query: %w", err)
	}

	return data, nil
}

func UnmarshalQuery(data []byte) (Query, error) {
	var doc queryDocument
	if err := json.Unmarshal(data, &doc); err != nil {
		return Query{}, fmt.Errorf("unmarshal query: %w", err)
	}

	q := Query{
		Version: doc.Version,
		From:    Target(doc.From),
		Limit:   doc.Limit,
		Offset:  doc.Offset,
	}

	if len(doc.Where) > 0 {
		where, err := unmarshalExpr(doc.Where)
		if err != nil {
			return Query{}, fmt.Errorf("unmarshal query where: %w", err)
		}
		q.Where = where
	}

	if len(doc.OrderBy) > 0 {
		q.OrderBy = make([]OrderExpr, 0, len(doc.OrderBy))
		for _, order := range doc.OrderBy {
			expr, err := unmarshalExpr(order.Expr)
			if err != nil {
				return Query{}, fmt.Errorf("unmarshal order expr: %w", err)
			}
			direction := SortDirection(order.Direction)
			if direction == "" {
				direction = SortAsc
			}
			q.OrderBy = append(q.OrderBy, OrderExpr{
				Expr:      expr,
				Direction: direction,
			})
		}
	}

	return q, nil
}

func marshalExpr(expr Expr) (json.RawMessage, error) {
	if expr == nil {
		return nil, nil
	}

	var payload any

	switch typed := expr.(type) {
	case *BoolExpr:
		terms := make([]json.RawMessage, 0, len(typed.Terms))
		for _, term := range typed.Terms {
			termJSON, err := marshalExpr(term)
			if err != nil {
				return nil, err
			}
			terms = append(terms, termJSON)
		}
		payload = map[string]any{
			"op":    string(typed.Op),
			"terms": terms,
		}
	case NotExpr:
		inner, err := marshalExpr(typed.Expr)
		if err != nil {
			return nil, err
		}
		payload = map[string]any{"not": inner}
	case *NotExpr:
		return marshalExpr(*typed)
	case Comparison:
		left, err := marshalExpr(typed.Left)
		if err != nil {
			return nil, err
		}
		right, err := marshalExpr(typed.Right)
		if err != nil {
			return nil, err
		}
		payload = map[string]any{
			"op":    string(typed.Op),
			"left":  json.RawMessage(left),
			"right": json.RawMessage(right),
		}
	case *Comparison:
		return marshalExpr(*typed)
	case InComparison:
		left, err := marshalExpr(typed.Left)
		if err != nil {
			return nil, err
		}
		values := make([]json.RawMessage, 0, len(typed.Values))
		for _, value := range typed.Values {
			valueJSON, err := marshalExpr(value)
			if err != nil {
				return nil, err
			}
			values = append(values, valueJSON)
		}
		payload = map[string]any{
			"in": map[string]any{
				"left":   json.RawMessage(left),
				"values": values,
			},
		}
	case *InComparison:
		return marshalExpr(*typed)
	case BetweenComparison:
		left, err := marshalExpr(typed.Left)
		if err != nil {
			return nil, err
		}
		lower, err := marshalExpr(typed.Lower)
		if err != nil {
			return nil, err
		}
		upper, err := marshalExpr(typed.Upper)
		if err != nil {
			return nil, err
		}
		payload = map[string]any{
			"between": map[string]any{
				"left":  json.RawMessage(left),
				"lower": json.RawMessage(lower),
				"upper": json.RawMessage(upper),
			},
		}
	case *BetweenComparison:
		return marshalExpr(*typed)
	case NullComparison:
		left, err := marshalExpr(typed.Left)
		if err != nil {
			return nil, err
		}
		payload = map[string]any{
			"is_null": map[string]any{
				"left": json.RawMessage(left),
				"not":  typed.Not,
			},
		}
	case *NullComparison:
		return marshalExpr(*typed)
	case RelationPredicate:
		body := map[string]any{
			"has_relation": typed.Type,
		}
		if typed.Direction != "" && typed.Direction != RelationAny {
			body["direction"] = string(typed.Direction)
		}
		payload = body
	case *RelationPredicate:
		return marshalExpr(*typed)
	case BucketPredicate:
		payload = map[string]string{"bucket": typed.Name}
	case *BucketPredicate:
		return marshalExpr(*typed)
	case FieldRef:
		payload = map[string]string{"field": typed.Name}
	case AttrRef:
		payload = map[string]string{"attr": typed.Path}
	case CastExpr:
		inner, err := marshalExpr(typed.Expr)
		if err != nil {
			return nil, err
		}
		payload = map[string]any{
			"cast": map[string]any{
				"expr": json.RawMessage(inner),
				"type": string(typed.Type),
			},
		}
	case StringLiteral:
		payload = map[string]string{"string": typed.Value}
	case IntLiteral:
		payload = map[string]int64{"integer": typed.Value}
	case FloatLiteral:
		payload = map[string]float64{"float": typed.Value}
	case BoolLiteral:
		payload = map[string]bool{"boolean": typed.Value}
	case TimestampLiteral:
		payload = map[string]string{"timestamp": typed.Value.UTC().Format(time.RFC3339Nano)}
	case NullLiteral:
		payload = map[string]bool{"null": true}
	case NowExpr:
		payload = map[string]bool{"now": true}
	case IntervalLiteral:
		payload = map[string]string{"interval": typed.Value}
	case ArithmeticExpr:
		left, err := marshalExpr(typed.Left)
		if err != nil {
			return nil, err
		}
		right, err := marshalExpr(typed.Right)
		if err != nil {
			return nil, err
		}
		payload = map[string]any{
			"arith": string(typed.Op),
			"left":  json.RawMessage(left),
			"right": json.RawMessage(right),
		}
	default:
		return nil, fmt.Errorf("marshal expr: unsupported type %T", expr)
	}

	data, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("marshal expr: %w", err)
	}

	return data, nil
}

func unmarshalExpr(data json.RawMessage) (Expr, error) {
	if len(data) == 0 {
		return nil, nil
	}

	var object map[string]json.RawMessage
	if err := json.Unmarshal(data, &object); err != nil {
		return nil, fmt.Errorf("unmarshal expr: %w", err)
	}

	if raw, ok := object["attr"]; ok {
		var path string
		if err := json.Unmarshal(raw, &path); err != nil {
			return nil, err
		}
		return AttrRef{Path: path}, nil
	}
	if raw, ok := object["field"]; ok {
		var name string
		if err := json.Unmarshal(raw, &name); err != nil {
			return nil, err
		}
		return FieldRef{Name: name}, nil
	}
	if raw, ok := object["string"]; ok {
		var value string
		if err := json.Unmarshal(raw, &value); err != nil {
			return nil, err
		}
		return StringLiteral{Value: value}, nil
	}
	if raw, ok := object["integer"]; ok {
		var value int64
		if err := json.Unmarshal(raw, &value); err != nil {
			return nil, err
		}
		return IntLiteral{Value: value}, nil
	}
	if raw, ok := object["float"]; ok {
		var value float64
		if err := json.Unmarshal(raw, &value); err != nil {
			return nil, err
		}
		return FloatLiteral{Value: value}, nil
	}
	if raw, ok := object["boolean"]; ok {
		var value bool
		if err := json.Unmarshal(raw, &value); err != nil {
			return nil, err
		}
		return BoolLiteral{Value: value}, nil
	}
	if raw, ok := object["timestamp"]; ok {
		var value string
		if err := json.Unmarshal(raw, &value); err != nil {
			return nil, err
		}
		parsed, err := time.Parse(time.RFC3339Nano, value)
		if err != nil {
			return nil, fmt.Errorf("unmarshal timestamp literal: %w", err)
		}
		return TimestampLiteral{Value: parsed.UTC()}, nil
	}
	if _, ok := object["null"]; ok {
		return NullLiteral{}, nil
	}
	if _, ok := object["now"]; ok {
		return NowExpr{}, nil
	}
	if raw, ok := object["interval"]; ok {
		var value string
		if err := json.Unmarshal(raw, &value); err != nil {
			return nil, err
		}
		return IntervalLiteral{Value: value}, nil
	}
	if raw, ok := object["has_relation"]; ok {
		var relationType string
		if err := json.Unmarshal(raw, &relationType); err != nil {
			return nil, err
		}
		predicate := RelationPredicate{
			Type:      relationType,
			Direction: RelationAny,
		}
		if directionRaw, ok := object["direction"]; ok {
			var direction string
			if err := json.Unmarshal(directionRaw, &direction); err != nil {
				return nil, err
			}
			predicate.Direction = RelationDirection(direction)
		}
		return predicate, nil
	}
	if raw, ok := object["bucket"]; ok {
		var bucketName string
		if err := json.Unmarshal(raw, &bucketName); err != nil {
			return nil, err
		}
		return BucketPredicate{Name: bucketName}, nil
	}
	if raw, ok := object["cast"]; ok {
		var body struct {
			Expr json.RawMessage `json:"expr"`
			Type string          `json:"type"`
		}
		if err := json.Unmarshal(raw, &body); err != nil {
			return nil, err
		}
		expr, err := unmarshalExpr(body.Expr)
		if err != nil {
			return nil, err
		}
		return CastExpr{Expr: expr, Type: ValueType(body.Type)}, nil
	}
	if raw, ok := object["not"]; ok {
		inner, err := unmarshalExpr(raw)
		if err != nil {
			return nil, err
		}
		return &NotExpr{Expr: inner}, nil
	}
	if raw, ok := object["in"]; ok {
		var body struct {
			Left   json.RawMessage   `json:"left"`
			Values []json.RawMessage `json:"values"`
		}
		if err := json.Unmarshal(raw, &body); err != nil {
			return nil, err
		}
		left, err := unmarshalExpr(body.Left)
		if err != nil {
			return nil, err
		}
		values := make([]Expr, 0, len(body.Values))
		for _, valueRaw := range body.Values {
			value, err := unmarshalExpr(valueRaw)
			if err != nil {
				return nil, err
			}
			values = append(values, value)
		}
		return &InComparison{Left: left, Values: values}, nil
	}
	if raw, ok := object["between"]; ok {
		var body struct {
			Left  json.RawMessage `json:"left"`
			Lower json.RawMessage `json:"lower"`
			Upper json.RawMessage `json:"upper"`
		}
		if err := json.Unmarshal(raw, &body); err != nil {
			return nil, err
		}
		left, err := unmarshalExpr(body.Left)
		if err != nil {
			return nil, err
		}
		lower, err := unmarshalExpr(body.Lower)
		if err != nil {
			return nil, err
		}
		upper, err := unmarshalExpr(body.Upper)
		if err != nil {
			return nil, err
		}
		return &BetweenComparison{Left: left, Lower: lower, Upper: upper}, nil
	}
	if raw, ok := object["is_null"]; ok {
		var body struct {
			Left json.RawMessage `json:"left"`
			Not  bool            `json:"not"`
		}
		if err := json.Unmarshal(raw, &body); err != nil {
			return nil, err
		}
		left, err := unmarshalExpr(body.Left)
		if err != nil {
			return nil, err
		}
		return &NullComparison{Left: left, Not: body.Not}, nil
	}
	if raw, ok := object["arith"]; ok {
		var op string
		if err := json.Unmarshal(raw, &op); err != nil {
			return nil, err
		}
		left, err := unmarshalExpr(object["left"])
		if err != nil {
			return nil, err
		}
		right, err := unmarshalExpr(object["right"])
		if err != nil {
			return nil, err
		}
		return ArithmeticExpr{
			Op:    ArithmeticOp(op),
			Left:  left,
			Right: right,
		}, nil
	}
	if raw, ok := object["op"]; ok {
		var op string
		if err := json.Unmarshal(raw, &op); err != nil {
			return nil, err
		}
		if termsRaw, ok := object["terms"]; ok {
			var terms []json.RawMessage
			if err := json.Unmarshal(termsRaw, &terms); err != nil {
				return nil, err
			}
			exprTerms := make([]Expr, 0, len(terms))
			for _, termRaw := range terms {
				term, err := unmarshalExpr(termRaw)
				if err != nil {
					return nil, err
				}
				exprTerms = append(exprTerms, term)
			}
			return &BoolExpr{Op: BoolOp(op), Terms: exprTerms}, nil
		}
		left, err := unmarshalExpr(object["left"])
		if err != nil {
			return nil, err
		}
		right, err := unmarshalExpr(object["right"])
		if err != nil {
			return nil, err
		}
		return Comparison{
			Op:    ComparisonOp(op),
			Left:  left,
			Right: right,
		}, nil
	}

	return nil, fmt.Errorf("unmarshal expr: unrecognized expression shape")
}
