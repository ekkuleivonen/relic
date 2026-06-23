package deps

import (
	"github.com/ekkuleivonen/relic/apps/api/internal/config"
	"github.com/jackc/pgx/v5/pgxpool"
)

type Dependencies struct {
	Config config.Config
	DB     *pgxpool.Pool
}
