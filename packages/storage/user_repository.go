package storage

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/jackc/pgx/v5"
)

type UserRepository interface {
	CreateUser(context.Context, CreateUserParams) (User, error)
	GetUser(context.Context, string) (User, error)
	GetUserByEmail(context.Context, string) (User, error)
	GetUserByOIDCSubject(context.Context, string) (User, error)
	ListUsers(context.Context) ([]User, error)
	UpdateUser(context.Context, UpdateUserParams) (User, error)
	CountUsers(context.Context) (int, error)
}

type UserStore struct {
	runner Runner
}

func NewUserStore(runner Runner) *UserStore {
	return &UserStore{runner: runner}
}

type UserRole string

const (
	UserRoleAdmin UserRole = "admin"
	UserRoleUser  UserRole = "user"
)

type User struct {
	ID           string
	Email        string
	DisplayName  string
	Role         UserRole
	PasswordHash *secrets.PasswordHash
	OIDCSubject  string
	DisabledAt   *time.Time
	CreatedAt    time.Time
	UpdatedAt    time.Time
}

type CreateUserParams struct {
	Email        string
	DisplayName  string
	Role         UserRole
	PasswordHash *secrets.PasswordHash
	OIDCSubject  string
}

type UpdateUserParams struct {
	ID           string
	DisplayName  *string
	Role         *UserRole
	PasswordHash *secrets.PasswordHash
	OIDCSubject  *string
	Disabled     *bool
}

func (s *UserStore) CreateUser(ctx context.Context, params CreateUserParams) (User, error) {
	id, err := newUserID()
	if err != nil {
		return User{}, err
	}

	email := strings.TrimSpace(strings.ToLower(params.Email))
	if email == "" {
		return User{}, fmt.Errorf("create user: email is required")
	}

	role := params.Role
	if role == "" {
		role = UserRoleUser
	}
	if role != UserRoleAdmin && role != UserRoleUser {
		return User{}, fmt.Errorf("create user: invalid role %q", role)
	}

	passwordHashJSON, err := encodePasswordHash(params.PasswordHash)
	if err != nil {
		return User{}, err
	}

	var oidcSubject *string
	if params.OIDCSubject != "" {
		oidcSubject = &params.OIDCSubject
	}

	row := s.runner.QueryRow(ctx, `
		INSERT INTO users (
			id, email, display_name, role, password_hash, oidc_subject
		) VALUES (
			$1, $2, NULLIF($3, ''), $4, $5, $6
		)
		RETURNING id, email, COALESCE(display_name, ''), role, password_hash, COALESCE(oidc_subject, ''),
			disabled_at, created_at, updated_at
	`, id, email, params.DisplayName, role, passwordHashJSON, oidcSubject)

	return scanUser(row)
}

func (s *UserStore) GetUser(ctx context.Context, id string) (User, error) {
	row := s.runner.QueryRow(ctx, `
		SELECT id, email, COALESCE(display_name, ''), role, password_hash, COALESCE(oidc_subject, ''),
			disabled_at, created_at, updated_at
		FROM users
		WHERE id = $1
	`, id)

	user, err := scanUser(row)
	if errors.Is(err, ErrNotFound) {
		return User{}, ErrNotFound
	}
	return user, err
}

func (s *UserStore) GetUserByEmail(ctx context.Context, email string) (User, error) {
	normalized := strings.TrimSpace(strings.ToLower(email))
	row := s.runner.QueryRow(ctx, `
		SELECT id, email, COALESCE(display_name, ''), role, password_hash, COALESCE(oidc_subject, ''),
			disabled_at, created_at, updated_at
		FROM users
		WHERE lower(email) = $1
	`, normalized)

	user, err := scanUser(row)
	if errors.Is(err, ErrNotFound) {
		return User{}, ErrNotFound
	}
	return user, err
}

func (s *UserStore) GetUserByOIDCSubject(ctx context.Context, subject string) (User, error) {
	row := s.runner.QueryRow(ctx, `
		SELECT id, email, COALESCE(display_name, ''), role, password_hash, COALESCE(oidc_subject, ''),
			disabled_at, created_at, updated_at
		FROM users
		WHERE oidc_subject = $1
	`, subject)

	user, err := scanUser(row)
	if errors.Is(err, ErrNotFound) {
		return User{}, ErrNotFound
	}
	return user, err
}

func (s *UserStore) ListUsers(ctx context.Context) ([]User, error) {
	rows, err := s.runner.Query(ctx, `
		SELECT id, email, COALESCE(display_name, ''), role, password_hash, COALESCE(oidc_subject, ''),
			disabled_at, created_at, updated_at
		FROM users
		ORDER BY created_at ASC
	`)
	if err != nil {
		return nil, fmt.Errorf("list users: %w", err)
	}
	defer rows.Close()

	users := make([]User, 0)
	for rows.Next() {
		user, err := scanUser(rows)
		if err != nil {
			return nil, err
		}
		users = append(users, user)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("list users: %w", err)
	}

	return users, nil
}

func (s *UserStore) UpdateUser(ctx context.Context, params UpdateUserParams) (User, error) {
	current, err := s.GetUser(ctx, params.ID)
	if err != nil {
		return User{}, err
	}

	displayName := current.DisplayName
	if params.DisplayName != nil {
		displayName = *params.DisplayName
	}

	role := current.Role
	if params.Role != nil {
		role = *params.Role
		if role != UserRoleAdmin && role != UserRoleUser {
			return User{}, fmt.Errorf("update user: invalid role %q", role)
		}
	}

	passwordHash := current.PasswordHash
	if params.PasswordHash != nil {
		passwordHash = params.PasswordHash
	}

	oidcSubject := current.OIDCSubject
	if params.OIDCSubject != nil {
		oidcSubject = *params.OIDCSubject
	}

	disabledAt := current.DisabledAt
	if params.Disabled != nil {
		if *params.Disabled {
			now := time.Now().UTC()
			disabledAt = &now
		} else {
			disabledAt = nil
		}
	}

	passwordHashJSON, err := encodePasswordHash(passwordHash)
	if err != nil {
		return User{}, err
	}

	var oidcSubjectParam *string
	if oidcSubject != "" {
		oidcSubjectParam = &oidcSubject
	}

	row := s.runner.QueryRow(ctx, `
		UPDATE users
		SET display_name = NULLIF($2, ''),
			role = $3,
			password_hash = $4,
			oidc_subject = $5,
			disabled_at = $6,
			updated_at = now()
		WHERE id = $1
		RETURNING id, email, COALESCE(display_name, ''), role, password_hash, COALESCE(oidc_subject, ''),
			disabled_at, created_at, updated_at
	`, params.ID, displayName, role, passwordHashJSON, oidcSubjectParam, disabledAt)

	return scanUser(row)
}

func (s *UserStore) CountUsers(ctx context.Context) (int, error) {
	row := s.runner.QueryRow(ctx, `SELECT count(*) FROM users`)
	var count int
	if err := row.Scan(&count); err != nil {
		return 0, fmt.Errorf("count users: %w", err)
	}
	return count, nil
}

func scanUser(row pgx.Row) (User, error) {
	var user User
	var passwordHashJSON []byte
	var disabledAt *time.Time

	err := row.Scan(
		&user.ID,
		&user.Email,
		&user.DisplayName,
		&user.Role,
		&passwordHashJSON,
		&user.OIDCSubject,
		&disabledAt,
		&user.CreatedAt,
		&user.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return User{}, ErrNotFound
	}
	if err != nil {
		return User{}, fmt.Errorf("scan user: %w", err)
	}

	user.DisabledAt = disabledAt
	if len(passwordHashJSON) > 0 {
		var hash secrets.PasswordHash
		if err := json.Unmarshal(passwordHashJSON, &hash); err != nil {
			return User{}, fmt.Errorf("decode user password hash: %w", err)
		}
		user.PasswordHash = &hash
	}

	return user, nil
}

func encodePasswordHash(hash *secrets.PasswordHash) ([]byte, error) {
	if hash == nil {
		return nil, nil
	}
	encoded, err := json.Marshal(hash)
	if err != nil {
		return nil, fmt.Errorf("encode password hash: %w", err)
	}
	return encoded, nil
}

func newUserID() (string, error) {
	random := make([]byte, 16)
	if _, err := rand.Read(random); err != nil {
		return "", fmt.Errorf("generate user id: %w", err)
	}

	return "user_" + hex.EncodeToString(random), nil
}
