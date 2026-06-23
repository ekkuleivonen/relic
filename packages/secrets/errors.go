package secrets

import "errors"

var (
	ErrInvalidKey           = errors.New("secrets: invalid key")
	ErrMissingKeyID         = errors.New("secrets: missing key id")
	ErrUnknownKeyID         = errors.New("secrets: unknown key id")
	ErrUnsupportedAlgorithm = errors.New("secrets: unsupported algorithm")
	ErrInvalidEnvelope      = errors.New("secrets: invalid envelope")
	ErrInvalidToken         = errors.New("secrets: invalid token")
	ErrInvalidTokenHash     = errors.New("secrets: invalid token hash")
	ErrTokenMismatch        = errors.New("secrets: token mismatch")
)
