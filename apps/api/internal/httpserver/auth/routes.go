package authhttp

import (
	"context"
	"net/http"

	"github.com/danielgtaylor/huma/v2"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
	"github.com/elei-io/pithosys/packages/auth"
)

func Register(api huma.API, dependencies deps.Dependencies, basePath string) {
	registerAuthConfigRoute(api, dependencies, basePath)
	if dependencies.Auth == nil {
		return
	}

	huma.Register(api, huma.Operation{
		OperationID: "get-auth-session",
		Method:      http.MethodGet,
		Path:        basePath + "/auth/session",
		Summary:     "Get current session",
		Tags:        []string{"Auth"},
	}, func(ctx context.Context, _ *struct{}) (*sessionOutput, error) {
		principal, ok := auth.PrincipalFromContext(ctx)
		if !ok {
			return nil, huma.Error401Unauthorized("Authentication is required.")
		}

		user, err := dependencies.Auth.GetUser(ctx, principal.ID)
		if err != nil {
			return nil, huma.Error401Unauthorized("Authentication is required.")
		}

		return &sessionOutput{
			Body: sessionResponse{User: userResponseFromStorage(user)},
		}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "set-auth-password",
		Method:      http.MethodPatch,
		Path:        basePath + "/auth/password",
		Summary:     "Set or change password",
		Tags:        []string{"Auth"},
	}, func(ctx context.Context, input *setPasswordInput) (*struct{}, error) {
		principal, ok := auth.PrincipalFromContext(ctx)
		if !ok {
			return nil, huma.Error401Unauthorized("Authentication is required.")
		}
		if input.Body.Password == "" {
			return nil, huma.Error400BadRequest("password is required")
		}

		if err := dependencies.Auth.SetPassword(ctx, principal.ID, input.Body.Password); err != nil {
			return nil, huma.Error500InternalServerError("Failed to update password.")
		}

		return nil, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "list-users",
		Method:      http.MethodGet,
		Path:        basePath + "/users",
		Summary:     "List users",
		Tags:        []string{"Auth"},
	}, func(ctx context.Context, _ *struct{}) (*listUsersOutput, error) {
		if err := requireAdmin(ctx); err != nil {
			return nil, err
		}

		users, err := dependencies.Auth.ListUsers(ctx)
		if err != nil {
			return nil, huma.Error500InternalServerError("Failed to list users.")
		}

		items := make([]sessionUserResponse, 0, len(users))
		for _, user := range users {
			items = append(items, userResponseFromStorage(user))
		}

		return &listUsersOutput{
			Body: listUsersResponse{Items: items},
		}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "create-user",
		Method:      http.MethodPost,
		Path:        basePath + "/users",
		Summary:     "Create user",
		Tags:        []string{"Auth"},
	}, func(ctx context.Context, input *createUserInput) (*userOutput, error) {
		if err := requireAdmin(ctx); err != nil {
			return nil, err
		}

		role := auth.RoleUser
		if input.Body.Role != "" {
			role = input.Body.Role
		}
		if role != auth.RoleAdmin && role != auth.RoleUser {
			return nil, huma.Error400BadRequest("role must be admin or user")
		}

		user, err := dependencies.Auth.CreateUser(ctx, auth.CreateUserParams{
			Email:       input.Body.Email,
			DisplayName: input.Body.DisplayName,
			Role:        role,
			Password:    input.Body.Password,
		})
		if err != nil {
			switch err {
			case auth.ErrUserExists:
				return nil, huma.Error409Conflict("A user with this email already exists.")
			default:
				return nil, huma.Error500InternalServerError("Failed to create user.")
			}
		}

		return &userOutput{Body: userResponseFromStorage(user)}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "update-user",
		Method:      http.MethodPatch,
		Path:        basePath + "/users/{id}",
		Summary:     "Update user",
		Tags:        []string{"Auth"},
	}, func(ctx context.Context, input *updateUserInput) (*userOutput, error) {
		if err := requireAdmin(ctx); err != nil {
			return nil, err
		}

		params := auth.UpdateUserParams{
			ID:          input.ID,
			DisplayName: input.Body.DisplayName,
			Disabled:    input.Body.Disabled,
		}
		if input.Body.Role != nil {
			role := *input.Body.Role
			if role != auth.RoleAdmin && role != auth.RoleUser {
				return nil, huma.Error400BadRequest("role must be admin or user")
			}
			params.Role = &role
		}
		if input.Body.Password != nil {
			params.Password = input.Body.Password
		}

		user, err := dependencies.Auth.UpdateUser(ctx, params)
		if err != nil {
			return nil, huma.Error500InternalServerError("Failed to update user.")
		}

		return &userOutput{Body: userResponseFromStorage(user)}, nil
	})
}

func registerAuthConfigRoute(api huma.API, dependencies deps.Dependencies, basePath string) {
	huma.Register(api, huma.Operation{
		OperationID: "get-auth-config",
		Method:      http.MethodGet,
		Path:        basePath + "/auth/config",
		Summary:     "Get auth configuration for the UI",
		Tags:        []string{"Auth"},
	}, func(_ context.Context, _ *struct{}) (*authConfigOutput, error) {
		oidcEnabled := dependencies.Auth != nil && dependencies.Auth.OIDCEnabled()
		return &authConfigOutput{
			Body: authConfigResponse{
				OIDCEnabled: oidcEnabled,
			},
		}, nil
	})
}

func requireAdmin(ctx context.Context) error {
	principal, ok := auth.PrincipalFromContext(ctx)
	if !ok {
		return huma.Error401Unauthorized("Authentication is required.")
	}
	if err := auth.RequireAdmin(principal); err != nil {
		return huma.Error403Forbidden("Admin access is required.")
	}
	return nil
}

type sessionOutput struct {
	Body sessionResponse
}

type setPasswordInput struct {
	Body struct {
		Password string `json:"password"`
	}
}

type listUsersOutput struct {
	Body listUsersResponse
}

type listUsersResponse struct {
	Items []sessionUserResponse `json:"items"`
}

type createUserInput struct {
	Body struct {
		Email       string    `json:"email"`
		DisplayName string    `json:"display_name,omitempty"`
		Role        auth.Role `json:"role,omitempty"`
		Password    string    `json:"password,omitempty"`
	}
}

type updateUserInput struct {
	ID   string `path:"id"`
	Body struct {
		DisplayName *string    `json:"display_name,omitempty"`
		Role        *auth.Role `json:"role,omitempty"`
		Disabled    *bool      `json:"disabled,omitempty"`
		Password    *string    `json:"password,omitempty"`
	}
}

type userOutput struct {
	Body sessionUserResponse
}

type authConfigOutput struct {
	Body authConfigResponse
}

type authConfigResponse struct {
	OIDCEnabled bool `json:"oidc_enabled"`
}
