#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
umask 077
mkdir -p .demo
if [ ! -f .demo/env ]; then
  {
    printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)"
    printf 'SUPERUSER_PASSWORD=%s\n' "$(openssl rand -hex 16)"
    printf 'SESSION_SECRET_BASE64=%s\n' "$(openssl rand -base64 32)"
    printf 'ENCRYPTION_KEY_BASE64=%s\n' "$(openssl rand -base64 32)"
    printf 'S3_ACCESS_KEY=%s\n' "$(openssl rand -hex 12)"
    printf 'S3_SECRET_KEY=%s\n' "$(openssl rand -hex 24)"
  } > .demo/env
fi
compose() { docker compose --env-file .demo/env "$@"; }
case "${1:-up}" in
  up)
    compose up --build -d --wait
    compose run --rm seed
    printf '\nDemo ready at http://localhost:8088\nLogin: admin@example.com\nPassword: see SUPERUSER_PASSWORD in .demo/env\n'
    ;;
  check) compose run --rm seed ;;
  down) compose down ;;
  logs) compose logs --tail=100 ;;
  *) printf 'Usage: %s [up|check|down|logs]\n' "$0" >&2; exit 2 ;;
esac
