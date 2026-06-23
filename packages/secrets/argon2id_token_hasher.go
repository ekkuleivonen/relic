package secrets

import (
	"crypto/rand"
	"crypto/subtle"
	"fmt"
	"io"

	"golang.org/x/crypto/argon2"
)

const (
	defaultArgon2idMemoryKiB = 64 * 1024
	defaultArgon2idTime      = 3
	defaultArgon2idThreads   = 1
	defaultTokenSaltBytes    = 16
	defaultTokenHashBytes    = 32
)

type Argon2idTokenHasher struct {
	params Argon2idParams
	random io.Reader
}

type Argon2idParams struct {
	MemoryKiB uint32
	Time      uint32
	Threads   uint8
	SaltBytes int
	HashBytes int
}

func NewArgon2idTokenHasher() *Argon2idTokenHasher {
	return newArgon2idTokenHasher(defaultArgon2idParams(), rand.Reader)
}

func newArgon2idTokenHasher(params Argon2idParams, random io.Reader) *Argon2idTokenHasher {
	if random == nil {
		random = rand.Reader
	}

	return &Argon2idTokenHasher{
		params: params,
		random: random,
	}
}

func (h *Argon2idTokenHasher) HashToken(token string) (TokenHash, error) {
	if token == "" {
		return TokenHash{}, ErrInvalidToken
	}
	if err := h.params.Validate(); err != nil {
		return TokenHash{}, err
	}

	salt := make([]byte, h.params.SaltBytes)
	if _, err := io.ReadFull(h.random, salt); err != nil {
		return TokenHash{}, fmt.Errorf("read token salt: %w", err)
	}

	return TokenHash{
		Algorithm: AlgorithmArgon2id,
		MemoryKiB: h.params.MemoryKiB,
		Time:      h.params.Time,
		Threads:   h.params.Threads,
		Salt:      salt,
		Hash:      argon2.IDKey([]byte(token), salt, h.params.Time, h.params.MemoryKiB, h.params.Threads, uint32(h.params.HashBytes)),
	}, nil
}

func (h *Argon2idTokenHasher) VerifyToken(token string, hash TokenHash) error {
	if token == "" {
		return ErrInvalidToken
	}
	if err := hash.Validate(); err != nil {
		return err
	}

	candidate := argon2.IDKey([]byte(token), hash.Salt, hash.Time, hash.MemoryKiB, hash.Threads, uint32(len(hash.Hash)))
	if subtle.ConstantTimeCompare(candidate, hash.Hash) != 1 {
		return ErrTokenMismatch
	}

	return nil
}

func defaultArgon2idParams() Argon2idParams {
	return Argon2idParams{
		MemoryKiB: defaultArgon2idMemoryKiB,
		Time:      defaultArgon2idTime,
		Threads:   defaultArgon2idThreads,
		SaltBytes: defaultTokenSaltBytes,
		HashBytes: defaultTokenHashBytes,
	}
}

func (p Argon2idParams) Validate() error {
	if p.MemoryKiB == 0 || p.Time == 0 || p.Threads == 0 || p.SaltBytes <= 0 || p.HashBytes <= 0 {
		return ErrInvalidTokenHash
	}

	return nil
}

func (h TokenHash) Validate() error {
	if h.Algorithm != AlgorithmArgon2id {
		return ErrUnsupportedAlgorithm
	}
	if h.MemoryKiB == 0 || h.Time == 0 || h.Threads == 0 || len(h.Salt) == 0 || len(h.Hash) == 0 {
		return ErrInvalidTokenHash
	}

	return nil
}
