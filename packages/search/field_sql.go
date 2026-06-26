package search

import "fmt"

func FieldSQLColumn(target Target, fieldName string) (string, error) {
	table, ok := targetTableName(target)
	if !ok {
		return "", fmt.Errorf("field SQL column: unsupported target %q", target)
	}

	for _, definition := range BuiltinTargetDefinitions() {
		if definition.Target != target {
			continue
		}
		for _, field := range definition.Fields {
			if field.Name == fieldName {
				return table + "." + field.Name, nil
			}
		}
	}

	return "", fmt.Errorf("field SQL column: unsupported field %q on target %q", fieldName, target)
}

func targetTableName(target Target) (string, bool) {
	switch target {
	case TargetObjects:
		return "objects", true
	case TargetRelations:
		return "relations", true
	default:
		return "", false
	}
}
