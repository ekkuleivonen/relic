package auth

import (
	"context"
	"fmt"
	"strings"

	"github.com/ekkuleivonen/relic/packages/secrets"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func EnsureBootstrapAdmin(
	ctx context.Context,
	users *storage.UserStore,
	hasher secrets.PasswordHasher,
	email string,
	password string,
) error {
	normalizedEmail := strings.TrimSpace(strings.ToLower(email))
	if normalizedEmail == "" {
		return fmt.Errorf("bootstrap admin: email is required")
	}

	existing, err := users.GetUserByEmail(ctx, normalizedEmail)
	if err != nil && err != storage.ErrNotFound {
		return fmt.Errorf("bootstrap admin: lookup user: %w", err)
	}

	var passwordHash *secrets.PasswordHash
	if password != "" {
		hash, err := hasher.HashPassword(password)
		if err != nil {
			return fmt.Errorf("bootstrap admin: hash password: %w", err)
		}
		passwordHash = &hash
	}

	if err == storage.ErrNotFound {
		if passwordHash == nil {
			return fmt.Errorf("bootstrap admin: password is required for initial admin user")
		}
		_, err := users.CreateUser(ctx, storage.CreateUserParams{
			Email:        normalizedEmail,
			Role:         storage.UserRoleAdmin,
			PasswordHash: passwordHash,
		})
		return err
	}

	role := storage.UserRoleAdmin
	update := storage.UpdateUserParams{
		ID:   existing.ID,
		Role: &role,
	}
	if passwordHash != nil {
		update.PasswordHash = passwordHash
	}

	_, err = users.UpdateUser(ctx, update)
	return err
}
