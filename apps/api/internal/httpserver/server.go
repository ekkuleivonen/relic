package httpserver

import (
	"net/http"
	"time"

	"github.com/danielgtaylor/huma/v2"
	"github.com/danielgtaylor/huma/v2/adapters/humago"
	authhttp "github.com/ekkuleivonen/relic/apps/api/internal/httpserver/auth"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/buckets"
	collectionshttp "github.com/ekkuleivonen/relic/apps/api/internal/httpserver/collections"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/deps"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/jobs"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/middleware"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/objects"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/search"
	settingshttp "github.com/ekkuleivonen/relic/apps/api/internal/httpserver/settings"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/system"
	"github.com/ekkuleivonen/relic/apps/api/internal/httpserver/upstreamcapture"
	bucketeventshttp "github.com/ekkuleivonen/relic/apps/api/internal/httpserver/bucketevents"
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
	authhttp.RegisterRawHandlers(mux, dependencies)
	api := humago.New(mux, apiConfig())
	authhttp.Register(api, dependencies, apiBasePath)
	buckets.Register(api, dependencies, apiBasePath)
	collectionshttp.Register(api, dependencies, apiBasePath)
	jobs.Register(api, dependencies, apiBasePath)
	objects.Register(api, dependencies, apiBasePath)
	search.Register(api, dependencies, apiBasePath)
	system.Register(api, dependencies, apiBasePath)
	upstreamcapture.Register(api, dependencies, apiBasePath)
	bucketeventshttp.Register(api, dependencies, apiBasePath)
	settingshttp.Register(api, dependencies, apiBasePath)

	return noStoreMiddleware(middleware.Auth(mux, dependencies))
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
			Name:        "Auth",
			Description: "Authentication, sessions, and user management.",
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
			Name:        "Collections",
			Description: "Saved RelicQL collections and derived object membership.",
		},
		{
			Name:        "Settings",
			Description: "Instance-wide configuration for upstream capture and related settings.",
		},
		{
			Name:        "Observability",
			Description: "Operational visibility into sync workloads and bucket events.",
		},
	}

	return cfg
}
