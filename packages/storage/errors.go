package storage

import "errors"

var (
	ErrNilPool        = errors.New("storage: nil postgres pool")
	ErrNotFound       = errors.New("storage: not found")
	ErrNotImplemented = errors.New("storage: not implemented")
)
