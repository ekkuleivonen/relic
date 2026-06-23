package deps

import (
	"github.com/ekkuleivonen/relic/apps/api/internal/config"
	"github.com/ekkuleivonen/relic/packages/storage"
)

type Dependencies struct {
	Config  config.Config
	Storage *storage.Store
}
