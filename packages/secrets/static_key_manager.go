package secrets

import (
	"context"
	"crypto/cipher"
	"crypto/rand"
	"fmt"
	"io"

	"golang.org/x/crypto/chacha20poly1305"
)

type StaticKeyManager struct {
	keyID  string
	aead   cipher.AEAD
	random io.Reader
}

func NewStaticKeyManager(keyID string, rawKey []byte) (*StaticKeyManager, error) {
	return newStaticKeyManager(keyID, rawKey, rand.Reader)
}

func newStaticKeyManager(keyID string, rawKey []byte, random io.Reader) (*StaticKeyManager, error) {
	if keyID == "" {
		return nil, ErrMissingKeyID
	}
	if len(rawKey) != chacha20poly1305.KeySize {
		return nil, fmt.Errorf("%w: got %d bytes, want %d", ErrInvalidKey, len(rawKey), chacha20poly1305.KeySize)
	}
	if random == nil {
		random = rand.Reader
	}

	aead, err := chacha20poly1305.NewX(rawKey)
	if err != nil {
		return nil, fmt.Errorf("create aead: %w", err)
	}

	return &StaticKeyManager{
		keyID:  keyID,
		aead:   aead,
		random: random,
	}, nil
}

func (m *StaticKeyManager) Encrypt(ctx context.Context, plaintext []byte) (Envelope, error) {
	if err := ctx.Err(); err != nil {
		return Envelope{}, err
	}

	nonce := make([]byte, chacha20poly1305.NonceSizeX)
	if _, err := io.ReadFull(m.random, nonce); err != nil {
		return Envelope{}, fmt.Errorf("read nonce: %w", err)
	}

	envelope := Envelope{
		KeyID:     m.keyID,
		Algorithm: AlgorithmXChaCha20Poly1305,
		Nonce:     nonce,
	}
	envelope.Ciphertext = m.aead.Seal(nil, nonce, plaintext, envelope.additionalData())

	return envelope, ctx.Err()
}

func (m *StaticKeyManager) Decrypt(ctx context.Context, envelope Envelope) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if envelope.KeyID != m.keyID {
		return nil, ErrUnknownKeyID
	}
	if envelope.Algorithm != AlgorithmXChaCha20Poly1305 {
		return nil, ErrUnsupportedAlgorithm
	}
	if len(envelope.Nonce) != chacha20poly1305.NonceSizeX || len(envelope.Ciphertext) == 0 {
		return nil, ErrInvalidEnvelope
	}

	plaintext, err := m.aead.Open(nil, envelope.Nonce, envelope.Ciphertext, envelope.additionalData())
	if err != nil {
		return nil, fmt.Errorf("decrypt secret: %w", err)
	}

	return plaintext, ctx.Err()
}

func (e Envelope) additionalData() []byte {
	return []byte(e.KeyID + "\x00" + e.Algorithm)
}
