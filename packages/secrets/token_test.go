package secrets

import (
	"errors"
	"strings"
	"testing"
)

func TestRandomTokenGenerator(t *testing.T) {
	generator := NewRandomTokenGenerator()

	token, err := generator.NewToken("relic_sk_live")
	if err != nil {
		t.Fatalf("NewToken returned error: %v", err)
	}

	if !strings.HasPrefix(token.Value, "relic_sk_live.") {
		t.Fatalf("Value = %q, want relic_sk_live prefix", token.Value)
	}
	if !strings.HasPrefix(token.Value, token.LookupPrefix+".") {
		t.Fatalf("Value = %q, want lookup prefix %q", token.Value, token.LookupPrefix)
	}
	if token.Value == token.LookupPrefix {
		t.Fatal("Value equals LookupPrefix")
	}

	lookupPrefix, err := LookupPrefixFromToken(token.Value)
	if err != nil {
		t.Fatalf("LookupPrefixFromToken returned error: %v", err)
	}
	if lookupPrefix != token.LookupPrefix {
		t.Fatalf("lookup prefix = %q, want %q", lookupPrefix, token.LookupPrefix)
	}
}

func TestRandomTokenGeneratorRejectsInvalidPrefix(t *testing.T) {
	generator := NewRandomTokenGenerator()

	if _, err := generator.NewToken(""); !errors.Is(err, ErrInvalidToken) {
		t.Fatalf("NewToken error = %v, want %v", err, ErrInvalidToken)
	}
	if _, err := generator.NewToken("relic.sk"); !errors.Is(err, ErrInvalidToken) {
		t.Fatalf("NewToken error = %v, want %v", err, ErrInvalidToken)
	}
}

func TestLookupPrefixFromTokenRejectsInvalidToken(t *testing.T) {
	for _, token := range []string{"", "only-prefix", "prefix.lookup", "prefix.lookup.secret.extra"} {
		if _, err := LookupPrefixFromToken(token); !errors.Is(err, ErrInvalidToken) {
			t.Fatalf("LookupPrefixFromToken(%q) error = %v, want %v", token, err, ErrInvalidToken)
		}
	}
}

func TestArgon2idTokenHasherRoundTrip(t *testing.T) {
	hasher := testTokenHasher()

	hash, err := hasher.HashToken("relic_sk_live.lookup.secret")
	if err != nil {
		t.Fatalf("HashToken returned error: %v", err)
	}

	if hash.Algorithm != AlgorithmArgon2id {
		t.Fatalf("Algorithm = %q, want %q", hash.Algorithm, AlgorithmArgon2id)
	}
	if string(hash.Hash) == "relic_sk_live.lookup.secret" {
		t.Fatal("Hash contains plaintext token")
	}

	if err := hasher.VerifyToken("relic_sk_live.lookup.secret", hash); err != nil {
		t.Fatalf("VerifyToken returned error: %v", err)
	}
}

func TestArgon2idTokenHasherRejectsWrongToken(t *testing.T) {
	hasher := testTokenHasher()

	hash, err := hasher.HashToken("relic_sk_live.lookup.secret")
	if err != nil {
		t.Fatalf("HashToken returned error: %v", err)
	}

	err = hasher.VerifyToken("relic_sk_live.lookup.other", hash)
	if !errors.Is(err, ErrTokenMismatch) {
		t.Fatalf("VerifyToken error = %v, want %v", err, ErrTokenMismatch)
	}
}

func TestArgon2idTokenHasherRejectsInvalidHash(t *testing.T) {
	hasher := testTokenHasher()

	err := hasher.VerifyToken("token", TokenHash{Algorithm: "other"})
	if !errors.Is(err, ErrUnsupportedAlgorithm) {
		t.Fatalf("VerifyToken error = %v, want %v", err, ErrUnsupportedAlgorithm)
	}

	err = hasher.VerifyToken("token", TokenHash{Algorithm: AlgorithmArgon2id})
	if !errors.Is(err, ErrInvalidTokenHash) {
		t.Fatalf("VerifyToken error = %v, want %v", err, ErrInvalidTokenHash)
	}
}

func TestArgon2idTokenHasherRejectsEmptyToken(t *testing.T) {
	hasher := testTokenHasher()

	if _, err := hasher.HashToken(""); !errors.Is(err, ErrInvalidToken) {
		t.Fatalf("HashToken error = %v, want %v", err, ErrInvalidToken)
	}
}

func testTokenHasher() *Argon2idTokenHasher {
	return newArgon2idTokenHasher(Argon2idParams{
		MemoryKiB: 1024,
		Time:      1,
		Threads:   1,
		SaltBytes: 16,
		HashBytes: 32,
	}, nil)
}
