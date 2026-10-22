#!/usr/bin/env bash
# Apply the Postgres schema migrations that have not been applied yet.
#
# The database's schema was originally created by docker-entrypoint-initdb.d,
# which only runs on the FIRST start of an empty volume. That means a new
# migration file added to api/migrations/ is silently ignored by an existing
# stack -- the exact failure mode this script exists to remove.
#
# Each file is applied at most once and recorded in the schema_migrations
# table. The migrations that predate that table (001-012) are baselined
# rather than re-run, because their DDL is not idempotent.
#
# Usage: ./scripts/apply_migrations.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1 \
   && [[ -d /Applications/Docker.app/Contents/Resources/bin ]]; then
  export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "error: docker compose is required" >&2
  exit 1
fi

DB_USER="${POSTGRES_USER:-dhanchakra}"
DB_NAME="${POSTGRES_DB:-dhanchakra}"

# Migrations that predate the schema_migrations ledger. They were applied by
# docker-entrypoint-initdb.d and their DDL is not idempotent, so they are
# recorded as applied instead of being re-run.
BASELINE=(
  "001_enable_extensions.sql"
  "002_users.sql"
  "003_cases.sql"
  "004_audit_log.sql"
  "005_ingestion_jobs.sql"
  "006_companies.sql"
  "007_case_exports.sql"
  "008_model_versions.sql"
  "009_alter_users.sql"
  "010_seed_users.sql"
  "011_entity_feedback.sql"
  "011_ingestion_job_statuses.sql"
  "012_user_role_limits.sql"
  "012_watchlist_notifications.sql"
)

psql_q() {
  "${COMPOSE[@]}" exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" "$@"
}

# Wait for Postgres to accept connections.
for _ in $(seq 1 30); do
  if psql_q -c "SELECT 1" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

psql_q -c "CREATE TABLE IF NOT EXISTS schema_migrations (
              name TEXT PRIMARY KEY,
              applied_at TIMESTAMESTZ NOT NULL DEFAULT now())" >/dev/null

for name in "${BASELINE[@]}"; do
  psql_q -c "INSERT INTO schema_migrations (name) VALUES ('$name')
             ON CONFLICT (name) DO NOTHING" >/dev/null
done

applied=0
skipped=0
for file in api/migrations/*.sql; do
  name="$(basename "$file")"
  already="$(psql_q -tAc "SELECT count(*) FROM schema_migrations WHERE name = '$name'")"
  if [[ "$already" == "1" ]]; then
    skipped=$((skipped + 1))
    continue
  fi
  echo "==> applying $name"
  "${COMPOSE[@]}" exec -T postgres \
    psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <"$file" >/dev/null
  psql_q -c "INSERT INTO schema_migrations (name) VALUES ('$name')" >/dev/null
  applied=$((applied + 1))
done

echo "migrations applied: $applied, already applied: $skipped"
