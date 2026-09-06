package deps

import (
	"github.com/elei-io/pithosys/apps/api/internal/config"
	"github.com/elei-io/pithosys/packages/auth"
	"github.com/elei-io/pithosys/packages/secrets"
	"github.com/elei-io/pithosys/packages/storage"
)

type Dependencies struct {
	Config  config.Config
	Secrets secrets.Manager
	Storage *storage.Store
	Auth    *auth.Service
}
