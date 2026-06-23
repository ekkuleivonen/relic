package httpserver

import (
	"net/http"
	"time"

	"github.com/ekkuleivonen/relic/apps/api/internal/config"
)

func New(cfg config.Config) *http.Server {
	return &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           Handler(),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
}

func Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", healthz)

	return mux
}

func healthz(w http.ResponseWriter, _ *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"status":"ok","service":"relic-api"}` + "\n"))
}
