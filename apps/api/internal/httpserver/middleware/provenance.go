package middleware

import (
	"context"

	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/packages/auth"
)

type RequestedBy struct {
	Type string
	ID   string
}

func RequestedByFromContext(ctx context.Context, dependencies deps.Dependencies) RequestedBy {
	principal, ok := auth.PrincipalFromContext(ctx)
	if !ok || dependencies.Auth == nil {
		return RequestedBy{Type: "api", ID: ""}
	}

	return RequestedBy{Type: "user", ID: principal.ID}
}
