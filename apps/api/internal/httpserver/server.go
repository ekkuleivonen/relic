package httpserver

import (
	"net/http"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humago"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/buckets"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/system"
)

const apiBasePath = "/api"

func New(dependencies deps.Dependencies) *http.Server {
	return &http.Server{
		Addr:              dependencies.Config.HTTPAddr,
		Handler:           Handler(dependencies),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
}

func Handler(dependencies deps.Dependencies) http.Handler {
	mux := http.NewServeMux()
	api := humago.New(mux, apiConfig())
	buckets.Register(api, dependencies, apiBasePath)
	system.Register(api, dependencies, apiBasePath)

	return mux
}

func apiConfig() huma.Config {
	cfg := huma.DefaultConfig("Relic API", "0.1.0")
	cfg.Info.Description = "Metadata and discovery API for object storage."
	cfg.OpenAPIPath = apiBasePath + "/openapi"
	cfg.DocsPath = apiBasePath + "/docs"
	cfg.SchemasPath = apiBasePath + "/schemas"
	cfg.Servers = []*huma.Server{
		{
			URL:         apiBasePath,
			Description: "Current Relic API server",
		},
	}
	cfg.Tags = []*huma.Tag{
		{
			Name:        "System",
			Description: "Operational endpoints for health, readiness, and diagnostics.",
		},
		{
			Name:        "Buckets",
			Description: "Bucket connection and catalog import endpoints.",
		},
	}

	return cfg
}
