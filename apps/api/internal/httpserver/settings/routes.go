package settingshttp

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/middleware"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func Register(api huma.API, dependencies deps.Dependencies, basePath string) {
	huma.Register(api, huma.Operation{
		OperationID: "list-settings",
		Method:      http.MethodGet,
		Path:        basePath + "/settings",
		Summary:     "List runtime settings",
		Tags:        []string{"Settings"},
	}, func(ctx context.Context, _ *listSettingsInput) (*listSettingsOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("storage is not configured")
		}

		settings, err := dependencies.Storage.Settings().List(ctx)
		if err != nil {
			return nil, err
		}

		return &listSettingsOutput{
			Body: settingListResponseFromStorage(settings),
		}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "patch-setting",
		Method:      http.MethodPatch,
		Path:        basePath + "/settings/{key}",
		Summary:     "Update a runtime setting",
		Tags:        []string{"Settings"},
	}, func(ctx context.Context, input *patchSettingInput) (*settingOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("storage is not configured")
		}

		principal, err := middleware.RequireAdminContext(ctx)
		if err != nil {
			return nil, err
		}

		if err := dependencies.Storage.Settings().Set(ctx, input.Key, input.Body.Value, principal.ID); err != nil {
			if errors.Is(err, storage.ErrSettingUnknown) {
				return nil, huma.Error422UnprocessableEntity("unknown setting key")
			}
			if errors.Is(err, storage.ErrSettingInvalidValue) {
				return nil, huma.Error422UnprocessableEntity(err.Error())
			}
			if errors.Is(err, storage.ErrNotFound) {
				return nil, huma.Error404NotFound("setting not found")
			}
			return nil, err
		}

		setting, err := dependencies.Storage.Settings().Get(ctx, input.Key)
		if err != nil {
			return nil, err
		}

		return &settingOutput{
			Body: settingResponseFromStorage(setting),
		}, nil
	})
}

type listSettingsInput struct{}

type listSettingsOutput struct {
	Body listSettingsResponse
}

type listSettingsResponse struct {
	Items []settingResponse `json:"items"`
}

type patchSettingInput struct {
	Key  string `path:"key"`
	Body struct {
		Value string `json:"value"`
	}
}

type settingOutput struct {
	Body settingResponse
}

type settingResponse struct {
	Key       string     `json:"key"`
	Value     string     `json:"value"`
	Encrypted bool       `json:"encrypted"`
	UpdatedAt time.Time  `json:"updated_at"`
	UpdatedBy *string    `json:"updated_by,omitempty"`
}

func settingListResponseFromStorage(settings []storage.Setting) listSettingsResponse {
	items := make([]settingResponse, 0, len(settings))
	for _, setting := range settings {
		items = append(items, settingResponseFromStorage(setting))
	}

	return listSettingsResponse{Items: items}
}

func settingResponseFromStorage(setting storage.Setting) settingResponse {
	return settingResponse{
		Key:       setting.Key,
		Value:     setting.Value,
		Encrypted: setting.Encrypted,
		UpdatedAt: setting.UpdatedAt,
		UpdatedBy: setting.UpdatedBy,
	}
}
