package auth

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"fmt"
	"io"
	"time"

	"github.com/ekkuleivonen/relic/packages/storage"
)

type SessionManager struct {
	random io.Reader
}

func NewSessionManager() *SessionManager {
	return &SessionManager{random: rand.Reader}
}

type SessionToken struct {
	Value     string
	TokenHash []byte
	ExpiresAt time.Time
}

func (m *SessionManager) NewSessionToken(ttl time.Duration) (SessionToken, error) {
	if ttl <= 0 {
		return SessionToken{}, fmt.Errorf("session ttl must be positive")
	}

	raw := make([]byte, 32)
	if _, err := io.ReadFull(m.random, raw); err != nil {
		return SessionToken{}, fmt.Errorf("generate session token: %w", err)
	}

	value := base64.RawURLEncoding.EncodeToString(raw)
	return SessionToken{
		Value:     value,
		TokenHash: HashSessionToken(value),
		ExpiresAt: time.Now().UTC().Add(ttl),
	}, nil
}

func HashSessionToken(token string) []byte {
	sum := sha256.Sum256([]byte(token))
	return sum[:]
}

func (m *SessionManager) CreateSession(
	ctx context.Context,
	sessions *storage.SessionStore,
	userID string,
	ttl time.Duration,
) (SessionToken, storage.Session, error) {
	token, err := m.NewSessionToken(ttl)
	if err != nil {
		return SessionToken{}, storage.Session{}, err
	}

	session, err := sessions.CreateSession(ctx, storage.CreateSessionParams{
		UserID:    userID,
		TokenHash: token.TokenHash,
		ExpiresAt: token.ExpiresAt,
	})
	if err != nil {
		return SessionToken{}, storage.Session{}, err
	}

	return token, session, nil
}

func (m *SessionManager) ResolveSession(
	ctx context.Context,
	sessions *storage.SessionStore,
	users *storage.UserStore,
	token string,
) (Principal, error) {
	if token == "" {
		return Principal{}, ErrUnauthorized
	}

	session, err := sessions.GetSessionByTokenHash(ctx, HashSessionToken(token))
	if err != nil {
		return Principal{}, ErrUnauthorized
	}

	if !session.ExpiresAt.After(time.Now().UTC()) {
		_ = sessions.DeleteSession(ctx, session.ID)
		return Principal{}, ErrUnauthorized
	}

	user, err := users.GetUser(ctx, session.UserID)
	if err != nil {
		return Principal{}, ErrUnauthorized
	}
	if user.DisabledAt != nil {
		return Principal{}, ErrUserDisabled
	}

	return PrincipalFromUser(user), nil
}

func (m *SessionManager) RevokeSession(ctx context.Context, sessions *storage.SessionStore, token string) error {
	if token == "" {
		return nil
	}
	return sessions.DeleteSessionByTokenHash(ctx, HashSessionToken(token))
}

func SessionTokenPreview(token string) string {
	if len(token) <= 8 {
		return token
	}
	return token[:4] + "..." + token[len(token)-4:]
}

func RandomState() (string, error) {
	raw := make([]byte, 16)
	if _, err := io.ReadFull(rand.Reader, raw); err != nil {
		return "", fmt.Errorf("generate oidc state: %w", err)
	}
	return hex.EncodeToString(raw), nil
}
