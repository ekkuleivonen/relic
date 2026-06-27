package httpserver

import (
	"net/http"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humago"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/buckets"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/jobs"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/objects"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/search"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/system"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/upstreamcapture"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/upstreamevents"
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
	jobs.Register(api, dependencies, apiBasePath)
	objects.Register(api, dependencies, apiBasePath)
	search.Register(api, dependencies, apiBasePath)
	system.Register(api, dependencies, apiBasePath)
	upstreamcapture.Register(api, dependencies, apiBasePath)
	upstreamevents.Register(api, dependencies, apiBasePath)

	return noStoreMiddleware(mux)
}

func noStoreMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		next.ServeHTTP(w, r)
	})
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
		{
			Name:        "Jobs",
			Description: "Durable background job run endpoints.",
		},
		{
			Name:        "Objects",
			Description: "Object catalog search and detail endpoints.",
		},
		{
			Name:        "Search",
			Description: "RelicQL validation and query endpoints.",
		},
		{
			Name:        "Settings",
			Description: "Instance-wide configuration for upstream capture and related settings.",
		},
		{
			Name:        "Upstream Events",
			Description: "Inbound upstream object notification endpoints.",
		},
	}

	return cfg
}
