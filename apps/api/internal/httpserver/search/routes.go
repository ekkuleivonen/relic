package search

import (
	"context"
	"net/http"
	"strings"

	"github.com/danielgtaylor/huma/v2"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/objects"
	"github.com/elei-io/pithosys/packages/search"
	"github.com/elei-io/pithosys/packages/storage"
)

func Register(api huma.API, dependencies deps.Dependencies, basePath string) {
	huma.Register(api, huma.Operation{
		OperationID: "execute-search",
		Method:      http.MethodPost,
		Path:        basePath + "/search",
		Summary:     "Execute PithosysQL search",
		Tags:        []string{"Search"},
	}, func(ctx context.Context, input *executeSearchInput) (*executeSearchOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("search dependencies are not configured")
		}

		queryText := strings.TrimSpace(input.Body.Query)
		if queryText == "" {
			return nil, huma.Error400BadRequest("query is required")
		}

		results, err := dependencies.Storage.SearchPithosysQL(ctx, queryText, storage.SearchScope{
			BucketID: strings.TrimSpace(input.Body.BucketID),
		})
		if err != nil {
			if search.IsValidationError(err) {
				return nil, huma.Error400BadRequest(err.Error())
			}
			return nil, huma.Error500InternalServerError(err.Error())
		}

		body := executeSearchBody{Objects: make([]objects.ObjectResponse, 0, len(results))}
		for _, object := range results {
			body.Objects = append(body.Objects, objects.ObjectResponseFromStorage(object))
		}

		return &executeSearchOutput{Body: body}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "validate-search",
		Method:      http.MethodPost,
		Path:        basePath + "/search/validate",
		Summary:     "Validate PithosysQL query",
		Tags:        []string{"Search"},
	}, func(ctx context.Context, input *validateSearchInput) (*validateSearchOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("search dependencies are not configured")
		}

		queryText := strings.TrimSpace(input.Body.Query)
		if queryText == "" {
			return nil, huma.Error400BadRequest("query is required")
		}

		bound, err := storage.ValidatePithosysQL(ctx, dependencies.Storage.AttributeCatalog(), queryText)
		if err != nil {
			if search.IsValidationError(err) {
				return nil, huma.Error400BadRequest(err.Error())
			}
			return nil, huma.Error500InternalServerError(err.Error())
		}

		return &validateSearchOutput{
			Body: validateSearchBody{
				Query:        queryText,
				QueryVersion: bound.Query.Version,
				From:         string(bound.Query.From),
				Dependencies: dependencyResponsesFromBound(bound),
			},
		}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "list-search-attributes",
		Method:      http.MethodGet,
		Path:        basePath + "/search/attributes",
		Summary:     "List known attribute paths",
		Tags:        []string{"Search"},
	}, func(ctx context.Context, _ *listSearchAttributesInput) (*listSearchAttributesOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("search dependencies are not configured")
		}

		entries, err := dependencies.Storage.AttributeCatalog().List(ctx)
		if err != nil {
			return nil, huma.Error500InternalServerError(err.Error())
		}

		attributes := make([]attributeResponse, 0, len(entries))
		for _, entry := range entries {
			attributes = append(attributes, attributeResponse{
				Path:   entry.Path,
				Type:   string(entry.ValueType),
				Source: string(entry.Source),
			})
		}

		return &listSearchAttributesOutput{
			Body: listSearchAttributesBody{Attributes: attributes},
		}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "list-search-relation-types",
		Method:      http.MethodGet,
		Path:        basePath + "/search/relation-types",
		Summary:     "List known relation types",
		Tags:        []string{"Search"},
	}, func(ctx context.Context, _ *listSearchRelationTypesInput) (*listSearchRelationTypesOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("search dependencies are not configured")
		}

		types, err := dependencies.Storage.ListSearchRelationTypes(ctx)
		if err != nil {
			return nil, huma.Error500InternalServerError(err.Error())
		}

		return &listSearchRelationTypesOutput{
			Body: listSearchRelationTypesBody{RelationTypes: types},
		}, nil
	})
}

type executeSearchInput struct {
	Body executeSearchRequest
}

type executeSearchRequest struct {
	Query    string `json:"query" doc:"PithosysQL query text" example:"FROM objects WHERE key = 'photos/a.jpg'"`
	BucketID string `json:"bucket_id,omitempty" doc:"Optional bucket scope" example:"bucket_0123456789abcdef0123456789abcdef"`
}

type executeSearchOutput struct {
	Body executeSearchBody
}

type executeSearchBody struct {
	Objects []objects.ObjectResponse `json:"objects"`
}

type validateSearchInput struct {
	Body validateSearchRequest
}

type validateSearchRequest struct {
	Query string `json:"query" doc:"PithosysQL query text" example:"FROM objects WHERE key = 'photos/a.jpg'"`
}

type validateSearchOutput struct {
	Body validateSearchBody
}

type validateSearchBody struct {
	Query        string                `json:"query"`
	QueryVersion string                `json:"query_version"`
	From         string                `json:"from"`
	Dependencies []dependencyResponse  `json:"dependencies"`
}

type dependencyResponse struct {
	Kind string `json:"kind"`
	Name string `json:"name"`
	Type string `json:"type,omitempty"`
}

// DependencyResponse is the shared OpenAPI shape for PithosysQL query dependencies.
type DependencyResponse = dependencyResponse

type listSearchAttributesInput struct{}

type listSearchAttributesOutput struct {
	Body listSearchAttributesBody
}

type listSearchAttributesBody struct {
	Attributes []attributeResponse `json:"attributes"`
}

type attributeResponse struct {
	Path   string `json:"path" example:"upstream.size"`
	Type   string `json:"type,omitempty" example:"integer"`
	Source string `json:"source,omitempty" example:"builtin"`
}

type listSearchRelationTypesInput struct{}

type listSearchRelationTypesOutput struct {
	Body listSearchRelationTypesBody
}

type listSearchRelationTypesBody struct {
	RelationTypes []string `json:"relation_types"`
}

func dependencyResponsesFromBound(bound search.BoundQuery) []DependencyResponse {
	responses := make([]DependencyResponse, 0, len(bound.Dependencies))
	for _, dependency := range bound.Dependencies {
		response := DependencyResponse{
			Kind: string(dependency.Kind),
			Name: dependency.Name,
		}
		if dependency.Type != "" {
			response.Type = string(dependency.Type)
		}
		responses = append(responses, response)
	}

	return responses
}
