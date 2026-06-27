package storage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
)

type SessionRepository interface {
	CreateSession(context.Context, CreateSessionParams) (Session, error)
	GetSessionByTokenHash(context.Context, []byte) (Session, error)
	DeleteSession(context.Context, string) error
	DeleteSessionByTokenHash(context.Context, []byte) error
	DeleteExpiredSessions(context.Context, time.Time) error
}

type SessionStore struct {
	runner Runner
}

func NewSessionStore(runner Runner) *SessionStore {
	return &SessionStore{runner: runner}
}

type Session struct {
	ID        string
	UserID    string
	TokenHash []byte
	ExpiresAt time.Time
	CreatedAt time.Time
}

type CreateSessionParams struct {
	UserID    string
	TokenHash []byte
	ExpiresAt time.Time
}

func (s *SessionStore) CreateSession(ctx context.Context, params CreateSessionParams) (Session, error) {
	if params.UserID == "" {
		return Session{}, fmt.Errorf("create session: user id is required")
	}
	if len(params.TokenHash) == 0 {
		return Session{}, fmt.Errorf("create session: token hash is required")
	}
	if params.ExpiresAt.IsZero() {
		return Session{}, fmt.Errorf("create session: expires_at is required")
	}

	id, err := newSessionID()
	if err != nil {
		return Session{}, err
	}

	row := s.runner.QueryRow(ctx, `
		INSERT INTO sessions (id, user_id, token_hash, expires_at)
		VALUES ($1, $2, $3, $4)
		RETURNING id, user_id, token_hash, expires_at, created_at
	`, id, params.UserID, params.TokenHash, params.ExpiresAt.UTC())

	return scanSession(row)
}

func (s *SessionStore) GetSessionByTokenHash(ctx context.Context, tokenHash []byte) (Session, error) {
	row := s.runner.QueryRow(ctx, `
		SELECT id, user_id, token_hash, expires_at, created_at
		FROM sessions
		WHERE token_hash = $1
	`, tokenHash)

	session, err := scanSession(row)
	if errors.Is(err, ErrNotFound) {
		return Session{}, ErrNotFound
	}
	return session, err
}

func (s *SessionStore) DeleteSession(ctx context.Context, id string) error {
	tag, err := s.runner.Exec(ctx, `DELETE FROM sessions WHERE id = $1`, id)
	if err != nil {
		return fmt.Errorf("delete session: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}

func (s *SessionStore) DeleteSessionByTokenHash(ctx context.Context, tokenHash []byte) error {
	_, err := s.runner.Exec(ctx, `DELETE FROM sessions WHERE token_hash = $1`, tokenHash)
	if err != nil {
		return fmt.Errorf("delete session by token hash: %w", err)
	}
	return nil
}

func (s *SessionStore) DeleteExpiredSessions(ctx context.Context, now time.Time) error {
	_, err := s.runner.Exec(ctx, `DELETE FROM sessions WHERE expires_at <= $1`, now.UTC())
	if err != nil {
		return fmt.Errorf("delete expired sessions: %w", err)
	}
	return nil
}

func scanSession(row pgx.Row) (Session, error) {
	var session Session
	err := row.Scan(
		&session.ID,
		&session.UserID,
		&session.TokenHash,
		&session.ExpiresAt,
		&session.CreatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return Session{}, ErrNotFound
	}
	if err != nil {
		return Session{}, fmt.Errorf("scan session: %w", err)
	}
	return session, nil
}

func newSessionID() (string, error) {
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		return "", fmt.Errorf("generate session id: %w", err)
	}

	return "session_" + hex.EncodeToString(random), nil
}
