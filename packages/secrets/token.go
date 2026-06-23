package secrets

import "strings"

const (
	AlgorithmArgon2id = "argon2id"

	defaultTokenLookupBytes = 8
	defaultTokenSecretBytes = 32
)

type TokenGenerator interface {
	NewToken(prefix string) (PlainToken, error)
}

type PlainToken struct {
	Value        string
	LookupPrefix string
}

type TokenHasher interface {
	HashToken(token string) (TokenHash, error)
	VerifyToken(token string, hash TokenHash) error
}

type TokenHash struct {
	Algorithm string `json:"algorithm"`
	MemoryKiB uint32 `json:"memory_kib"`
	Time      uint32 `json:"time"`
	Threads   uint8  `json:"threads"`
	Salt      []byte `json:"salt"`
	Hash      []byte `json:"hash"`
}

func LookupPrefixFromToken(token string) (string, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 || parts[0] == "" || parts[1] == "" || parts[2] == "" {
		return "", ErrInvalidToken
	}

	return parts[0] + "." + parts[1], nil
}
