package middleware

import (
	"context"
	"net"
	"net/http"
	"sync"
	"time"
)

func ProtectRequests(next http.Handler, webOrigin string) http.Handler {
	protection := http.NewCrossOriginProtection()
	if webOrigin != "" {
		if err := protection.AddTrustedOrigin(webOrigin); err != nil {
			// Invalid configuration must not silently bypass CSRF protection.
			return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				http.Error(w, "Invalid web origin configuration", http.StatusServiceUnavailable)
			})
		}
	}
	return protection.Handler(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "same-origin")
		r.Body = http.MaxBytesReader(w, r.Body, 1<<20)
		ctx, cancel := context.WithTimeout(r.Context(), 15*time.Second)
		defer cancel()
		next.ServeHTTP(w, r.WithContext(ctx))
	}))
}

// Bound password hashing work and per-client attempts. Forwarded headers are
// deliberately not trusted; configure additional rate limits at the proxy.
func LimitLogin(next http.Handler) http.Handler {
	type window struct {
		until    time.Time
		attempts int
	}
	var mu sync.Mutex
	clients := map[string]window{}
	active := make(chan struct{}, 4)
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		host, _, err := net.SplitHostPort(r.RemoteAddr)
		if err != nil {
			host = r.RemoteAddr
		}
		now := time.Now()
		mu.Lock()
		for key, entry := range clients {
			if !now.Before(entry.until) {
				delete(clients, key)
			}
		}
		entry, exists := clients[host]
		allowed := true
		if !exists {
			if len(clients) >= 1024 {
				allowed = false
			} else {
				entry.until = now.Add(time.Minute)
			}
		}
		if entry.attempts >= 10 {
			allowed = false
		}
		if allowed {
			entry.attempts++
			clients[host] = entry
		}
		mu.Unlock()
		if !allowed {
			w.Header().Set("Retry-After", "60")
			http.Error(w, "Too many login attempts", http.StatusTooManyRequests)
			return
		}
		select {
		case active <- struct{}{}:
			defer func() { <-active }()
			next.ServeHTTP(w, r)
		default:
			w.Header().Set("Retry-After", "1")
			http.Error(w, "Login is busy; retry shortly", http.StatusTooManyRequests)
		}
	})
}
