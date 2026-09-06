package auth

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/elei-io/pithosys/packages/storage"
	"github.com/jackc/pgx/v5/pgconn"
)

type Config struct {
	SuperuserEmail   string
	SuperuserPassword string
	SessionTTL       time.Duration
	SessionSecret    []byte
	SecureCookies    bool
	WebAppURL        string
	OIDC             OIDCConfig
}

type Service struct {
	cfg      Config
	store    *storage.Store
	hasher   secrets.PasswordHasher
	sessions *SessionManager
	oidc     *OIDCProvider
}

func NewService(cfg Config, store *storage.Store) (*Service, error) {
	oidcProvider, err := NewOIDCProvider(cfg.OIDC, cfg.SessionSecret)
	if err != nil {
		return nil, err
	}

	return &Service{
		cfg:      cfg,
		store:    store,
		hasher:   secrets.NewArgon2idPasswordHasher(),
		sessions: NewSessionManager(),
		oidc:     oidcProvider,
	}, nil
}

func (s *Service) Config() Config {
	return s.cfg
}

func (s *Service) OIDCEnabled() bool {
	return s.oidc != nil && s.oidc.Enabled()
}

func (s *Service) EnsureBootstrapAdmin(ctx context.Context) error {
	return EnsureBootstrapAdmin(ctx, s.store.Users(), s.hasher, s.cfg.SuperuserEmail, s.cfg.SuperuserPassword)
}

func (s *Service) Login(ctx context.Context, email, password string) (Principal, SessionToken, error) {
	user, err := s.store.Users().GetUserByEmail(ctx, email)
	if err != nil {
		return Principal{}, SessionToken{}, ErrInvalidCredentials
	}
	if user.DisabledAt != nil {
		return Principal{}, SessionToken{}, ErrUserDisabled
	}
	if user.PasswordHash == nil {
		return Principal{}, SessionToken{}, ErrPasswordNotSet
	}
	if err := s.hasher.VerifyPassword(password, *user.PasswordHash); err != nil {
		return Principal{}, SessionToken{}, ErrInvalidCredentials
	}

	token, _, err := s.sessions.CreateSession(ctx, s.store.Sessions(), user.ID, s.cfg.SessionTTL)
	if err != nil {
		return Principal{}, SessionToken{}, err
	}

	return PrincipalFromUser(user), token, nil
}

func (s *Service) Logout(ctx context.Context, sessionToken string) error {
	return s.sessions.RevokeSession(ctx, s.store.Sessions(), sessionToken)
}

func (s *Service) SessionFromToken(ctx context.Context, sessionToken string) (Principal, error) {
	return s.sessions.ResolveSession(ctx, s.store.Sessions(), s.store.Users(), sessionToken)
}

func (s *Service) GetUser(ctx context.Context, userID string) (storage.User, error) {
	return s.store.Users().GetUser(ctx, userID)
}

func (s *Service) ListUsers(ctx context.Context) ([]storage.User, error) {
	return s.store.Users().ListUsers(ctx)
}

func (s *Service) CreateUser(ctx context.Context, params CreateUserParams) (storage.User, error) {
	email := strings.TrimSpace(strings.ToLower(params.Email))
	if email == "" {
		return storage.User{}, fmt.Errorf("create user: email is required")
	}

	role := storage.UserRoleUser
	if params.Role == RoleAdmin {
		role = storage.UserRoleAdmin
	}

	var passwordHash *secrets.PasswordHash
	if params.Password != "" {
		hash, err := s.hasher.HashPassword(params.Password)
		if err != nil {
			return storage.User{}, err
		}
		passwordHash = &hash
	}

	user, err := s.store.Users().CreateUser(ctx, storage.CreateUserParams{
		Email:        email,
		DisplayName:  params.DisplayName,
		Role:         role,
		PasswordHash: passwordHash,
	})
	if err != nil {
		var pgErr *pgconn.PgError
		if errors.As(err, &pgErr) && pgErr.Code == "23505" {
			return storage.User{}, ErrUserExists
		}
		return storage.User{}, err
	}
	return user, nil
}

type CreateUserParams struct {
	Email       string
	DisplayName string
	Role        Role
	Password    string
}

type UpdateUserParams struct {
	ID          string
	Role        *Role
	Disabled    *bool
	Password    *string
	DisplayName *string
}

func (s *Service) UpdateUser(ctx context.Context, params UpdateUserParams) (storage.User, error) {
	update := storage.UpdateUserParams{
		ID:          params.ID,
		DisplayName: params.DisplayName,
		Disabled:    params.Disabled,
	}
	if params.Role != nil {
		role := storage.UserRoleUser
		if *params.Role == RoleAdmin {
			role = storage.UserRoleAdmin
		}
		update.Role = &role
	}
	if params.Password != nil {
		if *params.Password == "" {
			return storage.User{}, fmt.Errorf("update user: password cannot be empty")
		}
		hash, err := s.hasher.HashPassword(*params.Password)
		if err != nil {
			return storage.User{}, err
		}
		update.PasswordHash = &hash
	}

	user, err := s.store.Users().UpdateUser(ctx, update)
	if err != nil {
		return storage.User{}, err
	}
	return user, nil
}

func (s *Service) SetPassword(ctx context.Context, userID, password string) error {
	if password == "" {
		return fmt.Errorf("set password: password is required")
	}
	hash, err := s.hasher.HashPassword(password)
	if err != nil {
		return err
	}
	_, err = s.store.Users().UpdateUser(ctx, storage.UpdateUserParams{
		ID:           userID,
		PasswordHash: &hash,
	})
	return err
}

func (s *Service) OIDCStartURL() (string, string, time.Time, error) {
	if !s.OIDCEnabled() {
		return "", "", time.Time{}, ErrOIDCNotConfigured
	}

	state, err := RandomState()
	if err != nil {
		return "", "", time.Time{}, err
	}

	expiresAt := time.Now().UTC().Add(10 * time.Minute)
	signedState, err := s.oidc.SignState(state, expiresAt)
	if err != nil {
		return "", "", time.Time{}, err
	}

	return s.oidc.AuthCodeURL(state), signedState, expiresAt, nil
}

func (s *Service) OIDCCallback(ctx context.Context, code, signedState string) (Principal, SessionToken, error) {
	if !s.OIDCEnabled() {
		return Principal{}, SessionToken{}, ErrOIDCNotConfigured
	}

	if _, err := s.oidc.VerifyState(signedState); err != nil {
		return Principal{}, SessionToken{}, err
	}

	idToken, email, displayName, err := s.oidc.Exchange(ctx, code)
	if err != nil {
		return Principal{}, SessionToken{}, err
	}

	existingBySubject, subjectErr := s.store.Users().GetUserByOIDCSubject(ctx, idToken.Subject)
	if subjectErr == nil {
		if existingBySubject.DisabledAt != nil {
			return Principal{}, SessionToken{}, ErrUserDisabled
		}
		token, _, err := s.sessions.CreateSession(ctx, s.store.Sessions(), existingBySubject.ID, s.cfg.SessionTTL)
		if err != nil {
			return Principal{}, SessionToken{}, err
		}
		return PrincipalFromUser(existingBySubject), token, nil
	}
	if subjectErr != storage.ErrNotFound {
		return Principal{}, SessionToken{}, subjectErr
	}

	user, err := s.store.Users().GetUserByEmail(ctx, email)
	if err != nil {
		return Principal{}, SessionToken{}, ErrInvalidCredentials
	}
	if user.DisabledAt != nil {
		return Principal{}, SessionToken{}, ErrUserDisabled
	}
	if user.OIDCSubject != "" && user.OIDCSubject != idToken.Subject {
		return Principal{}, SessionToken{}, ErrOIDCSubjectConflict
	}

	subject := idToken.Subject
	update := storage.UpdateUserParams{
		ID:          user.ID,
		OIDCSubject: &subject,
	}
	if user.DisplayName == "" && displayName != "" {
		update.DisplayName = &displayName
	}
	user, err = s.store.Users().UpdateUser(ctx, update)
	if err != nil {
		return Principal{}, SessionToken{}, err
	}

	token, _, err := s.sessions.CreateSession(ctx, s.store.Sessions(), user.ID, s.cfg.SessionTTL)
	if err != nil {
		return Principal{}, SessionToken{}, err
	}

	return PrincipalFromUser(user), token, nil
}

func RequireAdmin(principal Principal) error {
	if !principal.IsAdmin() {
		return ErrForbidden
	}
	return nil
}
