package system

import (
	"context"
	"net/http"

	"github.com/danielgtaylor/huma/v2"
	"github.com/elei-io/pithosys/apps/api/internal/httpserver/deps"
)

func Register(api huma.API, _ deps.Dependencies, basePath string) {
	huma.Register(api, huma.Operation{
		OperationID: "healthz",
		Method:      http.MethodGet,
		Path:        basePath + "/healthz",
		Summary:     "Check API health",
		Tags:        []string{"System"},
	}, func(ctx context.Context, input *healthInput) (*healthOutput, error) {
		return &healthOutput{
			Body: healthBody{
				Service: "pithosys-api",
				Status:  "ok",
			},
		}, nil
	})
}

type healthInput struct{}

type healthOutput struct {
	Body healthBody
}

type healthBody struct {
	Service string `json:"service" example:"pithosys-api"`
	Status  string `json:"status" example:"ok"`
}
