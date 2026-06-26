package search

import (
	"fmt"
	"regexp"
	"strings"
)

const TypeInterval ValueType = "interval"

var intervalPattern = regexp.MustCompile(`(?i)^(\d+)\s+(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)$`)

func ParseIntervalValue(text string) (string, error) {
	matches := intervalPattern.FindStringSubmatch(strings.TrimSpace(text))
	if matches == nil {
		return "", fmt.Errorf("invalid interval %q", text)
	}

	quantity := matches[1]
	unit := normalizeIntervalUnit(matches[2])

	return quantity + " " + unit, nil
}

func normalizeIntervalUnit(unit string) string {
	switch strings.ToLower(unit) {
	case "second", "seconds":
		return "seconds"
	case "minute", "minutes":
		return "minutes"
	case "hour", "hours":
		return "hours"
	case "day", "days":
		return "days"
	case "week", "weeks":
		return "weeks"
	case "month", "months":
		return "months"
	case "year", "years":
		return "years"
	default:
		return unit
	}
}

func arithmeticResultType(op ArithmeticOp, left ValueType, right ValueType) (ValueType, error) {
	switch op {
	case ArithAdd:
		if left == TypeTimestamp && right == TypeInterval {
			return TypeTimestamp, nil
		}
		if left == TypeInterval && right == TypeTimestamp {
			return TypeTimestamp, nil
		}
	case ArithSub:
		if left == TypeTimestamp && right == TypeInterval {
			return TypeTimestamp, nil
		}
	}

	return "", fmt.Errorf("invalid arithmetic between %s and %s", left, right)
}

func formatIntervalSQL(value string) (string, error) {
	normalized, err := ParseIntervalValue(value)
	if err != nil {
		return "", err
	}
	if strings.Contains(normalized, "'") {
		return "", fmt.Errorf("invalid interval value")
	}

	return "interval '" + normalized + "'", nil
}

func FormatIntervalSQL(value string) (string, error) {
	return formatIntervalSQL(value)
}
