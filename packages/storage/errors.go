package storage

import "errors"

var (
	ErrNilPool                   = errors.New("storage: nil postgres pool")
	ErrNotFound                  = errors.New("storage: not found")
	ErrNotImplemented            = errors.New("storage: not implemented")
	ErrCatalogTypeConflict       = errors.New("storage: attribute catalog type conflict")
	ErrCaptureFieldNotFound      = errors.New("storage: upstream capture field not found")
	ErrCaptureFieldConflict      = errors.New("storage: upstream capture field conflict")
	ErrCaptureFieldRequired      = errors.New("storage: required upstream capture field cannot be disabled")
	ErrCaptureFieldPlatformOnly  = errors.New("storage: platform upstream capture field cannot be deleted")
	ErrCaptureFieldInvalidUpdate = errors.New("storage: invalid upstream capture field update")
	ErrSettingUnknown            = errors.New("storage: unknown setting key")
	ErrSettingInvalidValue       = errors.New("storage: invalid setting value")
)
