package secrets

import "context"

type Manager interface {
	Encrypt(context.Context, []byte) (Envelope, error)
	Decrypt(context.Context, Envelope) ([]byte, error)
}
