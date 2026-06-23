package storage

import "errors"

var (
	ErrNilPool        = errors.New("storage: nil postgres pool")
	ErrNotImplemented = errors.New("storage: not implemented")
)
