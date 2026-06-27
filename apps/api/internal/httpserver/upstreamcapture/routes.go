package upstreamcapture

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/packages/search"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func Register(api huma.API, dependencies deps.Dependencies, basePath string) {
	huma.Register(api, huma.Operation{
		OperationID: "list-upstream-capture-fields",
		Method:      http.MethodGet,
		Path:        basePath + "/upstream-capture-fields",
		Summary:     "List upstream capture fields",
		Tags:        []string{"Settings"},
	}, func(ctx context.Context, _ *listCaptureFieldsInput) (*listCaptureFieldsOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("storage is not configured")
		}

		fields, err := dependencies.Storage.UpstreamCaptureFields().List(ctx)
		if err != nil {
			return nil, err
		}

		return &listCaptureFieldsOutput{
			Body: captureFieldResponsesFromStorage(fields),
		}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "create-upstream-capture-field",
		Method:      http.MethodPost,
		Path:        basePath + "/upstream-capture-fields",
		Summary:     "Create user upstream capture field",
		Tags:        []string{"Settings"},
	}, func(ctx context.Context, input *createCaptureFieldInput) (*captureFieldOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("storage is not configured")
		}

		field, err := dependencies.Storage.UpstreamCaptureFields().CreateUser(ctx, storage.CreateUpstreamCaptureFieldParams{
			AttributePath: input.Body.AttributePath,
			Enabled:       enabledOrDefault(input.Body.Enabled),
			CaptureSource: storage.CaptureSource(input.Body.CaptureSource),
			ExtractorType: storage.CaptureExtractorType(input.Body.ExtractorType),
			ExtractorRef:  input.Body.ExtractorRef,
			ValueType:     search.ValueType(input.Body.ValueType),
		})
		if errors.Is(err, storage.ErrCaptureFieldConflict) {
			return nil, huma.Error409Conflict("upstream capture field already exists")
		}
		if err != nil {
			return nil, huma.Error422UnprocessableEntity(err.Error())
		}

		return &captureFieldOutput{
			Status: http.StatusCreated,
			Body:   captureFieldResponseFromStorage(field),
		}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "update-upstream-capture-field",
		Method:      http.MethodPatch,
		Path:        basePath + "/upstream-capture-fields/{id}",
		Summary:     "Update upstream capture field",
		Tags:        []string{"Settings"},
	}, func(ctx context.Context, input *updateCaptureFieldInput) (*captureFieldOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("storage is not configured")
		}

		field, err := dependencies.Storage.UpstreamCaptureFields().Update(ctx, input.ID, storage.UpdateUpstreamCaptureFieldParams{
			AttributePath: input.Body.AttributePath,
			Enabled:       input.Body.Enabled,
			CaptureSource: captureSourcePtr(input.Body.CaptureSource),
			ExtractorType: extractorTypePtr(input.Body.ExtractorType),
			ExtractorRef:  input.Body.ExtractorRef,
			ValueType:     valueTypePtr(input.Body.ValueType),
		})
		if errors.Is(err, storage.ErrCaptureFieldNotFound) {
			return nil, huma.Error404NotFound("upstream capture field not found")
		}
		if errors.Is(err, storage.ErrCaptureFieldRequired) {
			return nil, huma.Error422UnprocessableEntity(err.Error())
		}
		if errors.Is(err, storage.ErrCaptureFieldInvalidUpdate) {
			return nil, huma.Error422UnprocessableEntity(err.Error())
		}
		if errors.Is(err, storage.ErrCaptureFieldConflict) {
			return nil, huma.Error409Conflict("upstream capture field already exists")
		}
		if err != nil {
			return nil, err
		}

		return &captureFieldOutput{Body: captureFieldResponseFromStorage(field)}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "delete-upstream-capture-field",
		Method:      http.MethodDelete,
		Path:        basePath + "/upstream-capture-fields/{id}",
		Summary:     "Delete user upstream capture field",
		Tags:        []string{"Settings"},
	}, func(ctx context.Context, input *deleteCaptureFieldInput) (*deleteCaptureFieldOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("storage is not configured")
		}

		err := dependencies.Storage.UpstreamCaptureFields().DeleteUser(ctx, input.ID)
		if errors.Is(err, storage.ErrCaptureFieldNotFound) {
			return nil, huma.Error404NotFound("upstream capture field not found")
		}
		if errors.Is(err, storage.ErrCaptureFieldPlatformOnly) {
			return nil, huma.Error422UnprocessableEntity(err.Error())
		}
		if err != nil {
			return nil, err
		}

		return &deleteCaptureFieldOutput{Status: http.StatusNoContent}, nil
	})
}

type listCaptureFieldsInput struct{}

type listCaptureFieldsOutput struct {
	Body []CaptureFieldResponse
}

type createCaptureFieldInput struct {
	Body createCaptureFieldBody
}

type createCaptureFieldBody struct {
	AttributePath string `json:"attribute_path" example:"upstream.vendor.deployment_id"`
	Enabled       *bool  `json:"enabled,omitempty" example:"true"`
	CaptureSource string `json:"capture_source" example:"head"`
	ExtractorType string `json:"extractor_type" example:"response_header"`
	ExtractorRef  string `json:"extractor_ref" example:"x-acme-deployment-id"`
	ValueType     string `json:"value_type" example:"string"`
}

type updateCaptureFieldInput struct {
	ID   string `path:"id" example:"capture_0123456789abcdef"`
	Body updateCaptureFieldBody
}

type updateCaptureFieldBody struct {
	AttributePath *string `json:"attribute_path,omitempty" example:"upstream.vendor.deployment_id"`
	Enabled       *bool   `json:"enabled,omitempty" example:"false"`
	CaptureSource *string `json:"capture_source,omitempty" example:"head"`
	ExtractorType *string `json:"extractor_type,omitempty" example:"response_header"`
	ExtractorRef  *string `json:"extractor_ref,omitempty" example:"x-acme-deployment-id"`
	ValueType     *string `json:"value_type,omitempty" example:"string"`
}

type deleteCaptureFieldInput struct {
	ID string `path:"id" example:"capture_0123456789abcdef"`
}

type captureFieldOutput struct {
	Status int                  `json:"-"`
	Body   CaptureFieldResponse `json:"body"`
}

type deleteCaptureFieldOutput struct {
	Status int `json:"-"`
}

type CaptureFieldResponse struct {
	ID            string    `json:"id"`
	AttributePath string    `json:"attribute_path"`
	Enabled       bool      `json:"enabled"`
	Category      string    `json:"category"`
	Origin        string    `json:"origin"`
	CaptureSource string    `json:"capture_source"`
	ExtractorType string    `json:"extractor_type"`
	ExtractorRef  string    `json:"extractor_ref"`
	ValueType     string    `json:"value_type"`
	CreatedAt     time.Time `json:"created_at"`
	UpdatedAt     time.Time `json:"updated_at"`
}

func captureFieldResponsesFromStorage(fields []storage.UpstreamCaptureField) []CaptureFieldResponse {
	responses := make([]CaptureFieldResponse, 0, len(fields))
	for _, field := range fields {
		responses = append(responses, captureFieldResponseFromStorage(field))
	}

	return responses
}

func captureFieldResponseFromStorage(field storage.UpstreamCaptureField) CaptureFieldResponse {
	return CaptureFieldResponse{
		ID:            field.ID,
		AttributePath: field.AttributePath,
		Enabled:       field.Enabled,
		Category:      string(field.Category),
		Origin:        string(field.Origin),
		CaptureSource: string(field.CaptureSource),
		ExtractorType: string(field.ExtractorType),
		ExtractorRef:  field.ExtractorRef,
		ValueType:     string(field.ValueType),
		CreatedAt:     field.CreatedAt,
		UpdatedAt:     field.UpdatedAt,
	}
}

func captureSourcePtr(value *string) *storage.CaptureSource {
	if value == nil {
		return nil
	}

	typed := storage.CaptureSource(*value)
	return &typed
}

func extractorTypePtr(value *string) *storage.CaptureExtractorType {
	if value == nil {
		return nil
	}

	typed := storage.CaptureExtractorType(*value)
	return &typed
}

func valueTypePtr(value *string) *search.ValueType {
	if value == nil {
		return nil
	}

	typed := search.ValueType(*value)
	return &typed
}

func enabledOrDefault(value *bool) bool {
	if value == nil {
		return true
	}

	return *value
}
