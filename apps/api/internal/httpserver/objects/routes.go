package objects

import (
	"context"
	"errors"
	"net/http"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/packages/storage"
)

func Register(api huma.API, dependencies deps.Dependencies, basePath string) {
	huma.Register(api, huma.Operation{
		OperationID: "list-objects",
		Method:      http.MethodGet,
		Path:        basePath + "/objects",
		Summary:     "List objects",
		Tags:        []string{"Objects"},
	}, func(ctx context.Context, input *listObjectsInput) (*listObjectsOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("object dependencies are not configured")
		}

		objects, err := dependencies.Storage.Objects().ListObjects(ctx, storage.ListObjectsParams{
			BucketID:    input.BucketID,
			Prefix:      input.Prefix,
			ContentType: input.ContentType,
			KeyContains: input.KeyContains,
			Limit:       input.Limit,
			Offset:      input.Offset,
		})
		if err != nil {
			return nil, err
		}

		body := listObjectsBody{Objects: make([]objectResponse, 0, len(objects))}
		for _, object := range objects {
			body.Objects = append(body.Objects, objectResponseFromStorage(object))
		}

		return &listObjectsOutput{Body: body}, nil
	})

	huma.Register(api, huma.Operation{
		OperationID: "get-object",
		Method:      http.MethodGet,
		Path:        basePath + "/objects/{id}",
		Summary:     "Get object",
		Tags:        []string{"Objects"},
	}, func(ctx context.Context, input *getObjectInput) (*objectOutput, error) {
		if dependencies.Storage == nil {
			return nil, huma.Error500InternalServerError("object dependencies are not configured")
		}

		object, err := dependencies.Storage.Objects().GetObject(ctx, input.ID)
		if errors.Is(err, storage.ErrNotFound) {
			return nil, huma.Error404NotFound("object not found")
		}
		if err != nil {
			return nil, err
		}

		return &objectOutput{Body: objectResponseFromStorage(object)}, nil
	})
}

type listObjectsInput struct {
	BucketID    string `query:"bucket_id" example:"bucket_0123456789abcdef0123456789abcdef"`
	Prefix      string `query:"prefix" example:"photos/"`
	ContentType string `query:"content_type" example:"image/jpeg"`
	KeyContains string `query:"key_contains" example:"receipt"`
	Limit       int    `query:"limit" example:"100"`
	Offset      int    `query:"offset" example:"0"`
}

type getObjectInput struct {
	ID string `path:"id" example:"object_0123456789abcdef0123456789abcdef"`
}

type objectOutput struct {
	Body objectResponse
}

type listObjectsOutput struct {
	Body listObjectsBody
}

type listObjectsBody struct {
	Objects []objectResponse `json:"objects"`
}

type objectResponse struct {
	ID                  string                            `json:"id" example:"object_0123456789abcdef0123456789abcdef"`
	BucketID            string                            `json:"bucket_id" example:"bucket_0123456789abcdef0123456789abcdef"`
	Key                 string                            `json:"key" example:"photos/a.jpg"`
	VersionID           string                            `json:"version_id,omitempty" example:"provider-version"`
	Attributes          storage.ObjectAttributes          `json:"attributes"`
	AttributeProvenance storage.ObjectAttributeProvenance `json:"attribute_provenance"`
	FirstSeenAt         time.Time                         `json:"first_seen_at"`
	LastSeenAt          time.Time                         `json:"last_seen_at"`
	CreatedAt           time.Time                         `json:"created_at"`
	UpdatedAt           time.Time                         `json:"updated_at"`
}

func objectResponseFromStorage(object storage.Object) objectResponse {
	return objectResponse{
		ID:                  object.ID,
		BucketID:            object.BucketID,
		Key:                 object.Key,
		VersionID:           object.VersionID,
		Attributes:          object.Attributes,
		AttributeProvenance: object.AttributeProvenance,
		FirstSeenAt:         object.FirstSeenAt,
		LastSeenAt:          object.LastSeenAt,
		CreatedAt:           object.CreatedAt,
		UpdatedAt:           object.UpdatedAt,
	}
}
