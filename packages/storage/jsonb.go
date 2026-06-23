package storage

import (
	"encoding/json"
	"fmt"
	"strings"
)

type JSONBPath []string

func NewJSONBPath(parts ...string) (JSONBPath, error) {
	path := JSONBPath(parts)
	if err := path.Validate(); err != nil {
		return nil, err
	}

	return path, nil
}

func (p JSONBPath) Validate() error {
	if len(p) == 0 {
		return fmt.Errorf("jsonb path is empty")
	}

	for i, part := range p {
		if strings.TrimSpace(part) == "" {
			return fmt.Errorf("jsonb path segment %d is empty", i)
		}
	}

	return nil
}

func (p JSONBPath) TextArray() []string {
	return append([]string(nil), p...)
}

func (p JSONBPath) Dot() string {
	return strings.Join(p, ".")
}

type JSONBSet struct {
	Path  JSONBPath
	Value json.RawMessage
}

func NewJSONBSet(path JSONBPath, value any) (JSONBSet, error) {
	if err := path.Validate(); err != nil {
		return JSONBSet{}, err
	}

	encoded, err := json.Marshal(value)
	if err != nil {
		return JSONBSet{}, fmt.Errorf("marshal jsonb value: %w", err)
	}

	return JSONBSet{
		Path:  path,
		Value: encoded,
	}, nil
}

type JSONBPredicate struct {
	Path  JSONBPath
	Value json.RawMessage
}

func NewJSONBPredicate(path JSONBPath, value any) (JSONBPredicate, error) {
	if err := path.Validate(); err != nil {
		return JSONBPredicate{}, err
	}

	encoded, err := json.Marshal(value)
	if err != nil {
		return JSONBPredicate{}, fmt.Errorf("marshal jsonb predicate value: %w", err)
	}

	return JSONBPredicate{
		Path:  path,
		Value: encoded,
	}, nil
}
