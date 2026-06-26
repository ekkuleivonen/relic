package search

import (
	"fmt"
	"strings"
)

func ParseCastType(name string) (ValueType, error) {
	typ, ok := castTypeNames[strings.ToLower(strings.TrimSpace(name))]
	if !ok {
		return "", fmt.Errorf("unsupported cast type %q", name)
	}

	return typ, nil
}

var castTypeNames = map[string]ValueType{
	"text":        TypeString,
	"varchar":     TypeString,
	"string":      TypeString,
	"integer":     TypeInteger,
	"int":         TypeInteger,
	"bigint":      TypeInteger,
	"float":       TypeFloat,
	"real":        TypeFloat,
	"double":      TypeFloat,
	"boolean":     TypeBoolean,
	"bool":        TypeBoolean,
	"timestamp":   TypeTimestamp,
	"timestamptz": TypeTimestamp,
	"date":        TypeTimestamp,
}

func isValidCastOperand(expr Expr) bool {
	switch expr.(type) {
	case AttrRef, StringLiteral, TimestampLiteral:
		return true
	default:
		return false
	}
}
