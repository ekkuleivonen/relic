package auth

import "errors"

var (
	ErrInvalidCredentials = errors.New("auth: invalid credentials")
	ErrUnauthorized       = errors.New("auth: unauthorized")
	ErrForbidden          = errors.New("auth: forbidden")
	ErrUserDisabled       = errors.New("auth: user disabled")
	ErrUserNotFound       = errors.New("auth: user not found")
	ErrUserExists         = errors.New("auth: user already exists")
	ErrPasswordNotSet     = errors.New("auth: password not set")
	ErrOIDCNotConfigured  = errors.New("auth: oidc not configured")
	ErrOIDCStateInvalid   = errors.New("auth: oidc state invalid")
	ErrOIDCEmailMissing   = errors.New("auth: oidc email claim missing")
	ErrOIDCSubjectConflict = errors.New("auth: oidc subject conflict")
)
