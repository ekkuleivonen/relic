package collections

import (
	"context"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/middleware"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/objects"
	searchhttp "github.com/elei-io/pithosys/apps/api/internal/httpserver/search"
	"github.com/elei-io/pithosys/packages/search"
	"github.com/elei-io/pithosys/packages/storage"
)

func Register(api huma.API, dependencies deps.Dependencies, basePath string) {
	huma.Register(api, huma.Operation{
		OperationID: "list-collections",
		Method:      http.MethodGet,
		Path:        basePath + "/collections",
		Summary:     "List collections",
		Tags:        []string{"Collections"},
	}, func(ctx context.Context, input *listCollectionsInput) (*listCollectionsOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("collection dependencies are not configured")
		}

		collections, err := dependencies.Storage.Collections().ListCollections(ctx, storage.ListCollectionsParams{
			Limit:  input.Limit,
			Offset: input.Offset,
		})
		if err != nil {
			return nil, err
		}

		body := listCollectionsBody{Collections: make([]collectionResponse, 0, len(collections))}
		for _, collection := range collections {
			body.Collections = append(body.Collections, collectionResponseFromStorage(collection))
		}

		return &listCollectionsOutput{Body: body}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "create-collection",
		Method:      http.MethodPost,
		Path:        basePath + "/collections",
		Summary:     "Create collection",
		Tags:        []string{"Collections"},
	}, func(ctx context.Context, input *createCollectionInput) (*collectionOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("collection dependencies are not configured")
		}

		principal, err := middleware.RequireAdminContext(ctx)
		if err != nil {
			return nil, err
		}

		name := strings.TrimSpace(input.Body.Name)
		if name == "" {
			return nil, huma.Error400BadRequest("name is required")
		}

		queryText := strings.TrimSpace(input.Body.Query)
		if queryText == "" {
			return nil, huma.Error400BadRequest("query is required")
		}

		prepared, err := storage.PrepareCollectionQuery(ctx, dependencies.Storage.AttributeCatalog(), queryText)
		if err != nil {
			if search.IsValidationError(err) {
				return nil, huma.Error400BadRequest(err.Error())
			}
			return nil, err
		}

		collection, err := dependencies.Storage.Collections().CreateCollection(ctx, storage.CreateCollectionParams{
			Name:          name,
			Description:   strings.TrimSpace(input.Body.Description),
			QueryText:     queryText,
			QueryAST:      prepared.AST,
			QueryVersion:  prepared.QueryVersion,
			Dependencies:  storage.DependenciesFromSearch(prepared.Dependencies),
			Status:        storage.CollectionStatusValidEnum,
			OwnerUserID:   principal.ID,
			CreatedByType: "user",
			CreatedByID:   principal.ID,
		})
		if err != nil {
			return nil, err
		}

		return &collectionOutput{Body: collectionResponseFromStorage(collection)}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "get-collection",
		Method:      http.MethodGet,
		Path:        basePath + "/collections/{id}",
		Summary:     "Get collection",
		Tags:        []string{"Collections"},
	}, func(ctx context.Context, input *getCollectionInput) (*collectionOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("collection dependencies are not configured")
		}

		collection, err := dependencies.Storage.Collections().GetCollection(ctx, input.ID)
		if errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("collection not found")
		}
		if err != nil {
			return nil, err
		}

		return &collectionOutput{Body: collectionResponseFromStorage(collection)}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "update-collection",
		Method:      http.MethodPatch,
		Path:        basePath + "/collections/{id}",
		Summary:     "Update collection",
		Tags:        []string{"Collections"},
	}, func(ctx context.Context, input *updateCollectionInput) (*collectionOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("collection dependencies are not configured")
		}

		if _, err := middleware.RequireAdminContext(ctx); err != nil {
			return nil, err
		}

		params := storage.UpdateCollectionParams{ID: input.ID}

		if input.Body.Name != nil {
			name := strings.TrimSpace(*input.Body.Name)
			if name == "" {
				return nil, huma.Error400BadRequest("name cannot be empty")
			}
			params.Name = &name
		}
		if input.Body.Description != nil {
			description := strings.TrimSpace(*input.Body.Description)
			params.Description = &description
		}
		if input.Body.Query != nil {
			queryText := strings.TrimSpace(*input.Body.Query)
			if queryText == "" {
				return nil, huma.Error400BadRequest("query cannot be empty")
			}

			prepared, err := storage.PrepareCollectionQuery(ctx, dependencies.Storage.AttributeCatalog(), queryText)
			if err != nil {
				if search.IsValidationError(err) {
					return nil, huma.Error400BadRequest(err.Error())
				}
				return nil, err
			}

			params.QueryText = &queryText
			params.QueryAST = prepared.AST
			params.QueryVersion = &prepared.QueryVersion
			params.Dependencies = storage.DependenciesFromSearch(prepared.Dependencies)
			status := storage.CollectionStatusValidEnum
			params.Status = &status
			params.UpdateQuery = true
		}

		collection, err := dependencies.Storage.Collections().UpdateCollection(ctx, params)
		if errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("collection not found")
		}
		if err != nil {
			return nil, err
		}

		return &collectionOutput{Body: collectionResponseFromStorage(collection)}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "delete-collection",
		Method:      http.MethodDelete,
		Path:        basePath + "/collections/{id}",
		Summary:     "Delete collection",
		Tags:        []string{"Collections"},
	}, func(ctx context.Context, input *deleteCollectionInput) (*struct{}, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("collection dependencies are not configured")
		}

		if _, err := middleware.RequireAdminContext(ctx); err != nil {
			return nil, err
		}

		if err := dependencies.Storage.Collections().DeleteCollection(ctx, input.ID); errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("collection not found")
		} else if err != nil {
			return nil, err
		}

		return &struct{}{}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "list-collection-objects",
		Method:      http.MethodGet,
		Path:        basePath + "/collections/{id}/objects",
		Summary:     "List objects in a collection",
		Tags:        []string{"Collections"},
	}, func(ctx context.Context, input *listCollectionObjectsInput) (*listCollectionObjectsOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("collection dependencies are not configured")
		}

		collection, err := dependencies.Storage.Collections().GetCollection(ctx, input.ID)
		if errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("collection not found")
		}
		if err != nil {
			return nil, err
		}

		results, err := dependencies.Storage.SearchPithosysQL(ctx, collection.QueryText, storage.SearchScope{})
		if err != nil {
			if search.IsValidationError(err) {
				return nil, huma.Error400BadRequest(err.Error())
			}
			return nil, err
		}

		body := listCollectionObjectsBody{Objects: make([]objects.ObjectResponse, 0, len(results))}
		for _, object := range results {
			body.Objects = append(body.Objects, objects.ObjectResponseFromStorage(object))
		}

		return &listCollectionObjectsOutput{Body: body}, nil
	})
}

type listCollectionsInput struct {
	Limit  int `query:"limit" example:"100"`
	Offset int `query:"offset" example:"0"`
}

type listCollectionsOutput struct {
	Body listCollectionsBody
}

type listCollectionsBody struct {
	Collections []collectionResponse `json:"collections"`
}

type createCollectionInput struct {
	Body createCollectionBody
}

type createCollectionBody struct {
	Name        string `json:"name" example:"Finance PDFs"`
	Description string `json:"description,omitempty" example:"Objects owned by finance"`
	Query       string `json:"query" example:"FROM objects WHERE bucket('production') AND attr('user.owner') = 'finance'"`
}

type getCollectionInput struct {
	ID string `path:"id" example:"collection_0123456789abcdef0123456789abcdef"`
}

type updateCollectionInput struct {
	ID   string `path:"id" example:"collection_0123456789abcdef0123456789abcdef"`
	Body updateCollectionBody
}

type updateCollectionBody struct {
	Name        *string `json:"name,omitempty"`
	Description *string `json:"description,omitempty"`
	Query       *string `json:"query,omitempty"`
}

type deleteCollectionInput struct {
	ID string `path:"id" example:"collection_0123456789abcdef0123456789abcdef"`
}

type listCollectionObjectsInput struct {
	ID string `path:"id" example:"collection_0123456789abcdef0123456789abcdef"`
}

type listCollectionObjectsOutput struct {
	Body listCollectionObjectsBody
}

type listCollectionObjectsBody struct {
	Objects []objects.ObjectResponse `json:"objects"`
}

type collectionOutput struct {
	Body collectionResponse
}

type collectionResponse struct {
	ID             string                         `json:"id"`
	Name           string                         `json:"name"`
	Description    string                         `json:"description"`
	Query          string                         `json:"query"`
	QueryVersion   string                         `json:"query_version"`
	Dependencies   []searchhttp.DependencyResponse `json:"dependencies"`
	Status         string                         `json:"status"`
	OwnerUserID    string                         `json:"owner_user_id,omitempty"`
	CreatedByType  string                         `json:"created_by_type,omitempty"`
	CreatedByID    string                         `json:"created_by_id,omitempty"`
	CreatedAt      time.Time                      `json:"created_at"`
	UpdatedAt      time.Time                      `json:"updated_at"`
}

func collectionResponseFromStorage(collection storage.Collection) collectionResponse {
	response := collectionResponse{
		ID:            collection.ID,
		Name:          collection.Name,
		Description:   collection.Description,
		Query:         collection.QueryText,
		QueryVersion:  collection.QueryVersion,
		Status:        string(collection.Status),
		OwnerUserID:   collection.OwnerUserID,
		CreatedByType: collection.CreatedByType,
		CreatedByID:   collection.CreatedByID,
		CreatedAt:     collection.CreatedAt,
		UpdatedAt:     collection.UpdatedAt,
		Dependencies:  make([]searchhttp.DependencyResponse, 0, len(collection.Dependencies)),
	}

	for _, dependency := range collection.Dependencies {
		item := searchhttp.DependencyResponse{
			Kind: dependency.Kind,
			Name: dependency.Name,
		}
		if dependency.Type != "" {
			item.Type = dependency.Type
		}
		response.Dependencies = append(response.Dependencies, item)
	}

	return response
}
