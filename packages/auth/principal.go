package auth

import "github.com/elei-io/pithosys/packages/storage"

type Role string

const (
	RoleAdmin Role = "admin"
	RoleUser  Role = "user"
)

type Principal struct {
	ID    string
	Email string
	Role  Role
}

func PrincipalFromUser(user storage.User) Principal {
	return Principal{
		ID:    user.ID,
		Email: user.Email,
		Role:  Role(user.Role),
	}
}

func (p Principal) IsAdmin() bool {
	return p.Role == RoleAdmin
}
