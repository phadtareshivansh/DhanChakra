#!/usr/bin/env bash
# Load the curated sample dataset into the running stack and materialise
# analytics, so the dashboard, worklist and test suite all have data.
#
# Idempotent: the loaders MERGE, so re-running only updates existing nodes.
# Safe to run against a stack that is already up.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Docker Desktop on macOS keeps its CLI plugins here; harmless elsewhere.
if ! command -v docker >/dev/null 2>&1 \
   && [[ -d /Applications/Docker.app/Contents/Resources/bin ]]; then
  export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
fi

# Credentials/ports live in .env (never in the repo).
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

API_SERVICE="${API_SERVICE:-api}"
API_PORT="${API_PORT:-8000}"
API_BASE_URL="${API_BASE_URL:-http://localhost:${API_PORT}/api/v1}"
HEALTH_URL="${API_BASE_URL%/api/v1}/health"

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "error: neither 'docker compose' nor 'docker-compose' is on PATH" >&2
  exit 1
fi

step() { printf '==> %s\n' "$1"; }

step "waiting for the API ($HEALTH_URL)"
for _ in $(seq 1 60); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
if ! curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
  echo "error: API never became healthy — is the stack up? try: make up" >&2
  exit 1
fi

step "copying loaders + samples into the '$API_SERVICE' container"
"${COMPOSE[@]}" exec -T "$API_SERVICE" mkdir -p /tmp/boot
"${COMPOSE[@]}" cp ingestion/scripts/load_sample.py "$API_SERVICE:/tmp/boot/load_sample.py"
# Also drop the sample-filing generator where the live ingestion test looks
# for it, so that test runs instead of skipping.
"${COMPOSE[@]}" cp ingestion/scripts/make_sample_filings.py "$API_SERVICE:/tmp/make_sample_filings.py"
"${COMPOSE[@]}" cp ingestion/samples "$API_SERVICE:/tmp/boot/samples"

step "loading MCA sample (companies, directors, addresses, bank accounts)"
"${COMPOSE[@]}" exec -T "$API_SERVICE" \
  python /tmp/boot/load_sample.py --file /tmp/boot/samples/mca_sample.csv --type mca

step "loading GST sample (transactions, GSTIN filings)"
"${COMPOSE[@]}" exec -T "$API_SERVICE" \
  python /tmp/boot/load_sample.py --file /tmp/boot/samples/gst_sample.csv --type gst

step "loading e-Way Bill movement records (simulated movement-record source)"
"${COMPOSE[@]}" exec -T "$API_SERVICE" \
  python /tmp/boot/load_sample.py --file /tmp/boot/samples/eway_movement_sample.csv --type eway

step "structural analytics (rings, communities, centrality, heuristic risk)"
curl -fsS -X POST "$API_BASE_URL/analytics/structural" >/dev/null
echo "    ok"

step "GNN risk scoring"
if curl -fsS -X POST "$API_BASE_URL/analytics/gnn/predict" >/dev/null 2>&1; then
  echo "    ok"
else
  echo "    skipped — no GNN checkpoint yet; heuristic scores are retained"
fi

step "overview"
curl -fsS "$API_BASE_URL/stats/overview"
echo
