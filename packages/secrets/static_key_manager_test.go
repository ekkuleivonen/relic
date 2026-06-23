package secrets

import (
	"bytes"
	"context"
	"errors"
	"testing"

	"golang.org/x/crypto/chacha20poly1305"
)

func TestStaticKeyManagerRoundTrip(t *testing.T) {
	key := bytes.Repeat([]byte{1}, chacha20poly1305.KeySize)
	manager, err := NewStaticKeyManager("local-dev", key)
	if err != nil {
		t.Fatalf("NewStaticKeyManager returned error: %v", err)
	}

	plaintext := []byte(`{"access_key_id":"test","secret_access_key":"secret"}`)
	envelope, err := manager.Encrypt(context.Background(), plaintext)
	if err != nil {
		t.Fatalf("Encrypt returned error: %v", err)
	}

	if envelope.KeyID != "local-dev" {
		t.Fatalf("KeyID = %q, want local-dev", envelope.KeyID)
	}
	if envelope.Algorithm != AlgorithmXChaCha20Poly1305 {
		t.Fatalf("Algorithm = %q, want %q", envelope.Algorithm, AlgorithmXChaCha20Poly1305)
	}
	if bytes.Contains(envelope.Ciphertext, []byte("secret")) {
		t.Fatal("Ciphertext contains plaintext secret")
	}

	decrypted, err := manager.Decrypt(context.Background(), envelope)
	if err != nil {
		t.Fatalf("Decrypt returned error: %v", err)
	}
	if !bytes.Equal(decrypted, plaintext) {
		t.Fatalf("decrypted = %q, want %q", decrypted, plaintext)
	}
}

func TestStaticKeyManagerRejectsWrongKeyID(t *testing.T) {
	key := bytes.Repeat([]byte{1}, chacha20poly1305.KeySize)
	manager, err := NewStaticKeyManager("local-dev", key)
	if err != nil {
		t.Fatalf("NewStaticKeyManager returned error: %v", err)
	}

	envelope, err := manager.Encrypt(context.Background(), []byte("secret"))
	if err != nil {
		t.Fatalf("Encrypt returned error: %v", err)
	}
	envelope.KeyID = "other"

	_, err = manager.Decrypt(context.Background(), envelope)
	if !errors.Is(err, ErrUnknownKeyID) {
		t.Fatalf("Decrypt error = %v, want %v", err, ErrUnknownKeyID)
	}
}

func TestStaticKeyManagerRejectsInvalidKey(t *testing.T) {
	_, err := NewStaticKeyManager("local-dev", []byte("too-short"))
	if !errors.Is(err, ErrInvalidKey) {
		t.Fatalf("NewStaticKeyManager error = %v, want %v", err, ErrInvalidKey)
	}
}

func TestStaticKeyManagerDetectsTampering(t *testing.T) {
	key := bytes.Repeat([]byte{1}, chacha20poly1305.KeySize)
	manager, err := NewStaticKeyManager("local-dev", key)
	if err != nil {
		t.Fatalf("NewStaticKeyManager returned error: %v", err)
	}

	envelope, err := manager.Encrypt(context.Background(), []byte("secret"))
	if err != nil {
		t.Fatalf("Encrypt returned error: %v", err)
	}
	envelope.Ciphertext[0] ^= 0xff

	if _, err := manager.Decrypt(context.Background(), envelope); err == nil {
		t.Fatal("Decrypt returned nil error")
	}
}
