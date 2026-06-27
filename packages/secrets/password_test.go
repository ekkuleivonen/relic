package secrets

import "testing"

func TestArgon2idPasswordHasherHashAndVerify(t *testing.T) {
	hasher := NewArgon2idPasswordHasher()

	hash, err := hasher.HashPassword("correct horse battery staple")
	if err != nil {
		t.Fatalf("HashPassword returned error: %v", err)
	}

	if err := hasher.VerifyPassword("correct horse battery staple", hash); err != nil {
		t.Fatalf("VerifyPassword returned error: %v", err)
	}

	if err := hasher.VerifyPassword("wrong password", hash); err != ErrPasswordMismatch {
		t.Fatalf("VerifyPassword error = %v, want %v", err, ErrPasswordMismatch)
	}
}

func TestArgon2idPasswordHasherRejectsEmptyPassword(t *testing.T) {
	hasher := NewArgon2idPasswordHasher()

	if _, err := hasher.HashPassword(""); err != ErrInvalidPassword {
		t.Fatalf("HashPassword error = %v, want %v", err, ErrInvalidPassword)
	}
}
