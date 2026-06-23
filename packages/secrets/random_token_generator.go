package secrets

import (
	"crypto/rand"
	"encoding/base64"
	"fmt"
	"io"
	"strings"
)

type RandomTokenGenerator struct {
	lookupBytes int
	secretBytes int
	random      io.Reader
}

func NewRandomTokenGenerator() *RandomTokenGenerator {
	return newRandomTokenGenerator(defaultTokenLookupBytes, defaultTokenSecretBytes, rand.Reader)
}

func newRandomTokenGenerator(lookupBytes int, secretBytes int, random io.Reader) *RandomTokenGenerator {
	if random == nil {
		random = rand.Reader
	}

	return &RandomTokenGenerator{
		lookupBytes: lookupBytes,
		secretBytes: secretBytes,
		random:      random,
	}
}

func (g *RandomTokenGenerator) NewToken(prefix string) (PlainToken, error) {
	prefix = strings.TrimSpace(prefix)
	if prefix == "" || strings.Contains(prefix, ".") {
		return PlainToken{}, ErrInvalidToken
	}
	if g.lookupBytes <= 0 || g.secretBytes <= 0 {
		return PlainToken{}, ErrInvalidToken
	}

	lookup, err := randomURLString(g.random, g.lookupBytes)
	if err != nil {
		return PlainToken{}, fmt.Errorf("generate token lookup prefix: %w", err)
	}

	secret, err := randomURLString(g.random, g.secretBytes)
	if err != nil {
		return PlainToken{}, fmt.Errorf("generate token secret: %w", err)
	}

	lookupPrefix := prefix + "." + lookup
	return PlainToken{
		Value:        lookupPrefix + "." + secret,
		LookupPrefix: lookupPrefix,
	}, nil
}

func randomURLString(random io.Reader, size int) (string, error) {
	value := make([]byte, size)
	if _, err := io.ReadFull(random, value); err != nil {
		return "", err
	}

	return base64.RawURLEncoding.EncodeToString(value), nil
}
