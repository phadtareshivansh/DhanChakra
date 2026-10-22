#!/usr/bin/env bash
# Apply api/migrations/*.sql to a remote Postgres (Neon) in filename order.
#
# The local compose stack runs these automatically via
# /docker-entrypoint-initdb.d; a managed database does not, so run this once
# against the fresh Neon database:
#
#   DATABASE_URL='postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require' \
#     scripts/apply_migrations_neon.sh
#
# psql runs inside a throwaway postgres:16 container, so no local libpq
# installation is required.
set -euo pipefail

: "${DATABASE_URL:?Set DATABASE_URL to the Neon connection string}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
migrations_dir="$repo_root/api/migrations"

for migration in "$migrations_dir"/*.sql; do
  echo "==> $(basename "$migration")"
  docker run --rm \
    -v "$migrations_dir:/migrations:ro" \
    postgres:16 \
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "/migrations/$(basename "$migration")"
done

echo "All migrations applied."
