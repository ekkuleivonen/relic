package storage

import (
	"fmt"

	"github.com/ekkuleivonen/relic/packages/search"
)

func catalogValueTypeToDB(typ search.ValueType) (string, error) {
	switch typ {
	case search.TypeString:
		return "string", nil
	case search.TypeInteger:
		return "integer", nil
	case search.TypeFloat:
		return "float", nil
	case search.TypeBoolean:
		return "boolean", nil
	case search.TypeTimestamp:
		return "timestamp", nil
	case search.TypeUnknown:
		return "unknown", nil
	default:
		return "", fmt.Errorf("catalog value type %q cannot be stored", typ)
	}
}

func catalogValueTypeFromDB(value string) (search.ValueType, error) {
	switch value {
	case "string":
		return search.TypeString, nil
	case "integer":
		return search.TypeInteger, nil
	case "float":
		return search.TypeFloat, nil
	case "boolean":
		return search.TypeBoolean, nil
	case "timestamp":
		return search.TypeTimestamp, nil
	case "json":
		return search.TypeUnknown, nil
	case "unknown":
		return search.TypeUnknown, nil
	default:
		return "", fmt.Errorf("unknown catalog value type %q", value)
	}
}

func widenCatalogValueType(existing, incoming search.ValueType) (search.ValueType, bool) {
	if existing == incoming {
		return existing, true
	}
	if existing == search.TypeUnknown {
		return incoming, true
	}
	if incoming == search.TypeUnknown {
		return existing, true
	}
	if isCatalogNumericType(existing) && isCatalogNumericType(incoming) {
		if existing == search.TypeFloat || incoming == search.TypeFloat {
			return search.TypeFloat, true
		}
		return search.TypeInteger, true
	}

	return "", false
}

func isCatalogNumericType(typ search.ValueType) bool {
	return typ == search.TypeInteger || typ == search.TypeFloat
}
