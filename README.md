# Dhan-Chakra

**Graph-AI engine for shell-company invoice loops and GST fraud detection.**

Dhan-Chakra turns company, director, address and invoice records into a graph,
scores every company for fraud risk with a GNN, detects closed invoice rings,
explains *why* an entity is flagged in plain language, and gives an investigator
a case workflow with a full audit trail — end to end in one browser session.

> **Status: functional demo build (Phases 0–5 implemented).** The pipeline is
> real and exercised by the test suite against live Neo4j/PostgreSQL. It is
> **demo-scope**, not production-hardened: see
> [Demo scope vs. production scope](#demo-scope-vs-production-scope).

---

## What's implemented

| Area | What it does | Where |
|---|---|---|
| **Structural analytics** | Invoice **cycle (ring) detection**, weakly-connected components, communities, PageRank / betweenness / degree centrality, heuristic risk scoring with per-signal caps | `api/app/services/graph_service.py`, `graph/cypher/analytics.cypher` |
| **GNN risk scoring** | GraphSAGE-style model (plain PyTorch: two mean-aggregation SAGE layers) trained on the graph; scores every company 0–100, persisted back to the graph and surfaced as `risk_source=gnn_v1` | `api/app/services/gnn/` |
| **Entity resolution** | Normalises and links directors / addresses / bank accounts across companies (shared-director and shared-address signals) | `api/app/services/graph_service.py` (`/analytics/resolve`) |
| **Agentic ingestion** | Extracts `{company_name, cin, gstin, registered_address, director_name, din, shareholding}` from MCA-style **PDF filings** with **per-field confidence**; low-confidence fields are routed to manual review instead of auto-committed, then confirmed into the graph as `source=agentic` | `api/app/services/agentic_ingest.py`, `POST /ingest/document`, `/ingest/document/confirm` |
| **Case workflow** | Create / open / update / delete cases on a flagged entity, attach evidence, and **export a print-ready bundle** (preview + stored export records) | `api/app/services/case_service.py`, `frontend/src/pages/CasesView.tsx`, `CaseExport.tsx` |
| **Audit log** | Every consequential action is recorded (`ran_structural_analytics`, `ran_entity_resolution`, `ran_gnn_train`, `ran_gnn_predict`, `exported_case`, logins, …) and readable via `GET /audit` | `api/migrations/004_audit_log.sql`, `GET /api/v1/audit` |
| **Explainability** | `GET /entities/{id}/explain` returns a plain-language **reason** list plus **subgraph attribution** (`method="subgraph_attribution"`): the cycle, its member companies, total amount, invoice dates, shared directors/addresses, and a risk decomposition | `frontend/src/components/ExplainDrawer.tsx` |
| **Role-based auth** | Fixed 3-slot model: **one Super Admin** (`admin`) + **two standard users** (`analyst`). No self-registration. Super Admin manages the two slots; caps enforced at DB *and* service level | `api/app/services/auth_service.py`, `api/app/routes/admin.py`, migration `012_user_role_limits.sql` |

### The demo dataset: one flagged ring

The curated sample data contains exactly **one** fraud ring — six **Maya**
companies wired into a closed **6-hop** invoice loop (₹5,300,000 across
`INV-HERO-001..006`). All six score **100.0** with `risk_source=gnn_v1`.

```
Maya Infra → Trading → Logistics → Exports → Chemicals → Steel → Infra
```

The ring is *not* the whole dataset: it sits alongside clean companies so the
worklist, filters and the "outside the ring" explain path all behave honestly
(a company outside the ring returns `cycles: []`, no ring evidence).

---

## Quick start (fresh Mac)

```bash
# Prerequisites: Homebrew, Docker Desktop, Node 20+ and common CLI tools.
# If `docker-credential-desktop` is not found, prefix with:
#   export PATH="/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:$PATH"

cd <repo-root>
make env        # writes .env: strong random secrets + the 3 seeded login slots
make up         # build and start all services (Neo4j, Postgres, API, frontend)
make bootstrap  # load the sample dataset + run structural analytics and GNN scoring
make smoke      # verify the API (/health) and the frontend (:5173)
```

Then open **http://localhost:5173** and log in with the Super Admin credentials
from `.env` (`SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD`). Passwords are
**generated, never printed** — read them from `.env`, which is gitignored.

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API (OpenAPI docs) | http://localhost:8000/docs |
| Neo4j Browser | http://localhost:7474 (bolt://localhost:7687) |
| PostgreSQL | localhost:5432 / `${POSTGRES_DB}` |

All configuration lives in `.env` (gitignored; see `.env.example`).

### Everyday commands

```bash
make test       # run the API test suite in the container
make test-all   # seed the sample data, then run the full suite (no skips)
make restart    # reload the API after editing api/app/*.py (mounted read-only)
make logs       # tail all service logs
make reset      # DESTRUCTIVE: stop the stack and delete all data volumes
```

> `api/app` is mounted read-only into the API container, so Python edits need
> `make restart`. Test-only edits need `docker compose cp <file> api:/app/tests/`
> (or a rebuild). Frontend TypeScript checks run inside the container:
> `docker compose exec -T frontend sh -c "cd /app && ./node_modules/.bin/tsc --noEmit"`.

---

## Roles and demo logins

There is **no sign-up**. The system ships with three fixed slots, seeded from the
environment at API startup (rows are updated in place so user IDs stay stable):

| Slot | Role | Env vars |
|---|---|---|
| Super Admin (exactly 1) | `admin` | `SUPER_ADMIN_EMAIL` / `_PASSWORD` / `_NAME` |
| Standard user 1 | `analyst` | `USER1_*` |
| Standard user 2 | `analyst` | `USER2_*` |

- The caps (1 admin, max 2 analysts) are enforced by a partial unique index and
  a `BEFORE INSERT` trigger (migration `012_user_role_limits.sql`) **and**
  mirrored in the service layer for clean errors.
- `GET/PUT /admin/users`, `POST /admin/users/reset-password/{id}` are Super
  Admin only; a router that requires auth returns **401**, and a non-admin
  returns **403**. The Super Admin cannot edit or reset itself, and no request
  body can change a role.
- In production (`APP_ENV=production`) the API **refuses to boot** if any
  `SUPER_ADMIN_*` / `USER1_*` / `USER2_*` value is missing or a placeholder,
  if `JWT_SECRET` is weak, or if CORS is pointed at localhost.

---

## Account recovery

There is **no API endpoint** for recovering a lost Super Admin password, and no
self-service reset of any kind — that is deliberate. If the Super Admin password
is forgotten, an operator runs the break-glass CLI script on the host:

```bash
docker compose exec api python /scripts/reset_super_admin.py
```

It reads `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD` from the environment,
rehashes the password, and updates the **existing** admin row in place. It never
inserts a user and never touches the two analyst slots. Passwords are never
printed.

| Flag | Effect |
|---|---|
| `--dry-run` | Report what would change; write nothing (and no audit row) |
| `--allow-email-change` | Permit `SUPER_ADMIN_EMAIL` to re-point the admin row (refused if the new email already belongs to another user) |

**Exit codes**

| Code | Meaning |
|---|---|
| 0 | Success (or a `--dry-run` that would have succeeded) |
| 1 | Unexpected error |
| 2 | `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD` missing or a placeholder |
| 3 | No admin row exists (run `make bootstrap` to seed it) |
| 4 | More than one admin row exists (invariant broken) |
| 5 | Admin email differs and `--allow-email-change` was not given |
| 6 | `--allow-email-change` given, but the new email is already taken |

A real (non-dry-run) recovery writes a row to `audit_log` in the same
transaction as the password update: `action = 'super_admin_recovery'`,
`user_id = NULL` (out-of-band operator action), `entity_id` = the admin's id, and
`details = {"via": "cli", "email_changed": <bool>, "dry_run": false}`. The
password and its hash are never recorded.

---

## API surface

Base path: `/api/v1`.

```
Auth            POST /auth/login                GET  /auth/me
Admin           GET  /admin/users               PUT  /admin/users/{id}
                POST /admin/users/reset-password/{id}
Entities        GET  /entities/search           GET  /entities/{id}
                GET  /entities/{id}/network     GET  /entities/{id}/timeline
                GET  /entities/{id}/explain
Worklist/stats  GET  /worklist                  GET  /stats/overview
Analytics       GET  /analytics/loops           GET  /analytics/loops/{cin}
                GET  /analytics/centrality/{cin} POST /analytics/structural
                POST /analytics/resolve          POST /analytics/risk
                GET  /analytics/risk/{job_id}    POST /analytics/wcc
GNN             POST /analytics/gnn/train        POST /analytics/gnn/predict
                GET  /analytics/gnn/model
Ingestion       POST /ingest/csv                 POST /ingest/document
                POST /ingest/document/confirm    GET  /ingest/status/{job_id}
Cases           GET/POST /cases                  GET/PATCH/DELETE /cases/{id}
                POST /cases/{id}/export          GET  /cases/{id}/export/preview
                GET  /cases/{id}/exports
Audit           GET  /audit
Health          GET  /health
```

---

## Demo scope vs. production scope

**Built and working (demo-scope)**

- Real graph analytics, a real (small) GNN, real entity resolution, real
  agentic PDF extraction with confidence gating.
- Real auth with fixed roles and DB-enforced caps; real audit trail.
- Deterministic curated dataset with a single, explainable fraud ring.
- Explainability is structural (subgraph attribution) — honest about what it is.

**Deliberately not production-grade (yet)**

- **Data scale.** The sample set is small (single-digit companies/edges by
  design, for a 3-minute demo). Not tuned or load-tested for lakhs of invoices.
- **Explainability.** `method="subgraph_attribution"` is rule/structure-based
  feature attribution, **not** learned GNNExplainer.
- **Ingestion.** The default `AGENT_INGEST_BACKEND=rules` is deterministic
  labeled-line extraction that works offline. An optional `llm` backend exists
  (OpenAI-compatible: `AGENT_LLM_URL` / `AGENT_LLM_KEY`) and degrades to
  `rules` when unconfigured.
- **Risk scoring.** The heuristic score is a weighted sum with per-signal caps;
  the GNN adds a learned signal. Neither is a calibrated fraud probability.
- **Ops/security.** Fixed 3 user slots and a single JWT signing key suit a
  demo; production needs an IdP, key rotation, rate limiting, and secret
  management. Seeding is off in production unless `ALLOW_DEMO_SEED=true`.
- **Migrations.** SQL files are applied by Postgres `docker-entrypoint-initdb.d`
  on a **fresh volume**; there is no migration-tracking table. Schema changes to
  a live DB are applied manually (see `api/migrations/`).

---

## Project structure

```
project-root/
├── docker-compose.yml          # neo4j + postgres + api + frontend
├── Makefile                    # env / up / bootstrap / test / smoke / reset …
├── .env.example                # every knob, placeholders only (no secrets)
├── api/
│   ├── app/
│   │   ├── main.py             # app wiring + production startup gate
│   │   ├── config.py           # pydantic-settings; all knobs + safety gates
│   │   ├── deps.py             # DB/Neo4j sessions + auth dependencies
│   │   ├── models/schemas.py
│   │   ├── routes/             # entities.py, admin.py
│   │   └── services/           # graph_service, auth_service, case_service,
│   │       └── gnn/            # ingestion_service, agentic_ingest; GNN pkg
│   ├── migrations/             # 001…012 (users, cases, audit, jobs, roles…)
│   └── tests/                  # API + live-graph + auth + privacy + config suites
├── graph/cypher/               # constraints, seed, analytics
├── ingestion/
│   ├── scripts/                # load_sample.py, make_sample_filings.py
│   ├── samples/                # MCA/GST CSVs + 5 sample filing PDFs
│   └── guards/                 # synthetic_pans.txt (privacy test allowlist)
├── analytics/notebooks/        # structural prototype
├── frontend/src/
│   ├── App.tsx                 # routes (auth-gated)
│   ├── components/             # Layout, ExplainDrawer, RiskBadge …
│   ├── pages/                  # Dashboard, Worklist, EntityDetail,
│   │                           #   LoopsView, CasesView, CaseExport,
│   │                           #   Ingest, Settings, AdminUsers, Login
│   ├── utils/api.ts
│   └── types/api.ts
├── scripts/                    # init_env.py, bootstrap_demo_data.sh
├── shared/types/
└── docs/                       # demo.md (+ design docs, kept in repo)
```

---

## Verification

```bash
set -a; source .env; set +a     # credentials come from .env only

docker compose ps               # all services healthy
curl http://localhost:8000/health
make test                       # API suite (some live tests skip if not seeded)
make test-all                   # seed first, then run everything (no skips)
```

The suite covers the API surface, live graph analytics, entity resolution, the
GNN write-back, the agentic document flow, auth/roles, the production startup
gate, and a privacy guard that scans sample data for real PAN/Aadhaar shapes.

## Notes for deployment

Set `APP_ENV=production`, generate a strong `JWT_SECRET`
(`python3 -c "import secrets; print(secrets.token_urlsafe(48))"`), set
`CORS_ORIGINS` to real origins, and leave `SEED_DEMO_USERS`/`ALLOW_DEMO_SEED`
off. The startup gate refuses to boot on placeholder secrets, localhost CORS, or
missing seeded-slot credentials.
