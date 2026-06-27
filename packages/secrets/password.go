package secrets

import (
	"crypto/rand"
	"crypto/subtle"
	"fmt"
	"io"

	"golang.org/x/crypto/argon2"
)

const (
	defaultPasswordMemoryKiB = 64 * 1024
	defaultPasswordTime      = 3
	defaultPasswordThreads   = 1
	defaultPasswordSaltBytes = 16
	defaultPasswordHashBytes = 32
)

type PasswordHasher interface {
	HashPassword(password string) (PasswordHash, error)
	VerifyPassword(password string, hash PasswordHash) error
}

type PasswordHash struct {
	Algorithm string `json:"algorithm"`
	MemoryKiB uint32 `json:"memory_kib"`
	Time      uint32 `json:"time"`
	Threads   uint8  `json:"threads"`
	Salt      []byte `json:"salt"`
	Hash      []byte `json:"hash"`
}

type Argon2idPasswordHasher struct {
	params Argon2idPasswordParams
	random io.Reader
}

type Argon2idPasswordParams struct {
	MemoryKiB uint32
	Time      uint32
	Threads   uint8
	SaltBytes int
	HashBytes int
}

func NewArgon2idPasswordHasher() *Argon2idPasswordHasher {
	return newArgon2idPasswordHasher(defaultArgon2idPasswordParams(), rand.Reader)
}

func newArgon2idPasswordHasher(params Argon2idPasswordParams, random io.Reader) *Argon2idPasswordHasher {
	if random == nil {
		random = rand.Reader
	}

	return &Argon2idPasswordHasher{
		params: params,
		random: random,
	}
}

func (h *Argon2idPasswordHasher) HashPassword(password string) (PasswordHash, error) {
	if password == "" {
		return PasswordHash{}, ErrInvalidPassword
	}
	if err := h.params.Validate(); err != nil {
		return PasswordHash{}, err
	}

	salt := make([]byte, h.params.SaltBytes)
	if _, err := io.ReadFull(h.random, salt); err != nil {
		return PasswordHash{}, fmt.Errorf("read password salt: %w", err)
	}

	return PasswordHash{
		Algorithm: AlgorithmArgon2id,
		MemoryKiB: h.params.MemoryKiB,
		Time:      h.params.Time,
		Threads:   h.params.Threads,
		Salt:      salt,
		Hash: argon2.IDKey(
			[]byte(password),
			salt,
			h.params.Time,
			h.params.MemoryKiB,
			h.params.Threads,
			uint32(h.params.HashBytes),
		),
	}, nil
}

func (h *Argon2idPasswordHasher) VerifyPassword(password string, hash PasswordHash) error {
	if password == "" {
		return ErrInvalidPassword
	}
	if err := hash.Validate(); err != nil {
		return err
	}

	candidate := argon2.IDKey(
		[]byte(password),
		hash.Salt,
		hash.Time,
		hash.MemoryKiB,
		hash.Threads,
		uint32(len(hash.Hash)),
	)
	if subtle.ConstantTimeCompare(candidate, hash.Hash) != 1 {
		return ErrPasswordMismatch
	}

	return nil
}

func defaultArgon2idPasswordParams() Argon2idPasswordParams {
	return Argon2idPasswordParams{
		MemoryKiB: defaultPasswordMemoryKiB,
		Time:      defaultPasswordTime,
		Threads:   defaultPasswordThreads,
		SaltBytes: defaultPasswordSaltBytes,
		HashBytes: defaultPasswordHashBytes,
	}
}

func (p Argon2idPasswordParams) Validate() error {
	if p.MemoryKiB == 0 || p.Time == 0 || p.Threads == 0 || p.SaltBytes <= 0 || p.HashBytes <= 0 {
		return ErrInvalidPasswordHash
	}

	return nil
}

func (h PasswordHash) Validate() error {
	if h.Algorithm != AlgorithmArgon2id {
		return ErrUnsupportedAlgorithm
	}
	if h.MemoryKiB == 0 || h.Time == 0 || h.Threads == 0 || len(h.Salt) == 0 || len(h.Hash) == 0 {
		return ErrInvalidPasswordHash
	}

	return nil
}
