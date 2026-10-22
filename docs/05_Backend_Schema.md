# Backend Schema
## Dhan-Chakra — Graph & Relational Data Model

**Version:** 1.0 | **Companion to:** 02_TRD.md

---

## 1. Overview

Dhan-Chakra uses **two data stores**:
1. **Neo4j (property graph)** — the source of truth for entities, relationships, structural analytics, and GNN features. This is where all fraud-detection logic runs.
2. **PostgreSQL (relational)** — application-layer metadata: users, worklist/case state, audit trail, ingestion job status. Neo4j is not used for things it's a poor fit for (user auth, workflow state, append-only logs).

## 2. Neo4j Graph Schema

### 2.1 Node Labels & Properties

**`:Company`**
| Property | Type | Notes |
|---|---|---|
| `id` | string (UUID) | internal primary key |
| `cin` | string | Corporate Identification Number (unique, indexed) |
| `gstin` | string | GSTIN if registered (indexed) |
| `name` | string | |
| `incorporation_date` | date | |
| `status` | string | active / struck-off / dormant |
| `authorized_capital` | float | |
| `paid_up_capital` | float | |
| `nic_code` | string | sector classification |
| `roc` | string | Registrar of Companies jurisdiction |
| `risk_score` | float | 0–100, written by GNN scoring job |
| `community_id` | string | Louvain/Leiden cluster id, written by structural analytics job |
| `pagerank` | float | written by centrality job |
| `betweenness` | float | written by centrality job |
| `created_at` / `updated_at` | datetime | |

**`:Director`**
| Property | Type | Notes |
|---|---|---|
| `id` | string (UUID) | |
| `din` | string | Director Identification Number (unique, indexed) |
| `name` | string | |
| `pan_hash` | string | hashed, never raw PAN |

**`:Address`**
| Property | Type | Notes |
|---|---|---|
| `id` | string (UUID) | |
| `normalized_address` | string | canonicalized for exact-match resolution (indexed) |
| `raw_address` | string | as originally provided |
| `state` | string | |
| `lat` / `lng` | float, nullable | optional |

**`:BankAccount`**
| Property | Type | Notes |
|---|---|---|
| `id` | string (UUID) | |
| `ifsc` | string | |
| `account_hash` | string | hashed, never raw account number |

**`:Transaction`** *(modeled as a node, not just an edge, so an invoice carries rich attributes and can itself be queried/flagged)*
| Property | Type | Notes |
|---|---|---|
| `id` | string (UUID) | |
| `invoice_no` | string | |
| `amount` | float | |
| `tax_amount` | float | |
| `date` | date | |
| `hsn_sac_code` | string | |
| `eway_bill_ref` | string, nullable | the e-Way Bill the invoice cites; joins to `:EWayBillMovement.ref` |

**`:EWayBillMovement`** *(the SIMULATED movement-record source — see §2.1.1)*
| Property | Type | Notes |
|---|---|---|
| `id` | string (UUID) | internal primary key |
| `ref` | string | the e-Way Bill reference (unique, indexed) — the join key |
| `amount` | float | the value the movement record says actually moved |
| `movement_date` | date, nullable | |
| `from_state` / `to_state` | string, nullable | origin and destination state |
| `vehicle_no` | string, nullable | |
| `distance_km` | float, nullable | |
| `source` | string | the source's name — always `simulated` here, not a live feed |

**`:EWayBillMovementSource`** *(singleton — the feed's identity and coverage window)*
| Property | Type | Notes |
|---|---|---|
| `id` | string | always `active` — the rule needs one authoritative feed |
| `name` | string | the source's name (`simulated` for the sample feed) |
| `covers_from` | date, nullable | first invoice date the feed covers |
| `covers_to` | date, nullable | last invoice date the feed covers |
| `record_count` | int | how many movement records the source loaded |
| `loaded_at` | datetime | |

### 2.1.1 The e-Way Bill movement-record source

The fraud signal is **not** "this invoice has no e-Way Bill reference string". It is
**"this high-value invoice has no matching e-Way Bill movement record"**.

A reference is only a *claim* that goods moved; the movement record is the document
that backs it. An invoice can cite a reference that no movement record supports, and
that gap is the signal. The two are joined by property, not by relationship:

```
Transaction.eway_bill_ref  ->  EWayBillMovement.ref
```

There is deliberately no relationship between them: a property join cannot go stale,
and an analyst can always see both sides of the gap without traversing a graph.

A high-value invoice (`amount >= eway_high_value_threshold`, default ₹50,000) fails to
match in one of three ways:

| Reason | Meaning |
|---|---|
| `no_ref` | the invoice cites no e-Way Bill at all |
| `no_movement_record` | the invoice cites one, but no movement record backs it |
| `amount_mismatch` | a movement record exists, but its value differs from the invoice value by more than the tolerance |

The tolerance is `eway_amount_tolerance_pct` (5%) of the invoice value, with an
absolute floor of `eway_amount_tolerance_min` (₹1,000) so small invoices are not
flagged on rounding. The rule is defined **once**, in
`api/app/services/eway_service.py`, and is shared by the GNN feature extractor, the
heuristic risk score and the explain endpoint.

**The feed must declare what it covers.** The singleton `:EWayBillMovementSource`
node records the invoice period the feed covers (`covers_from` / `covers_to`).
"No matching movement record" is asserted **only** for invoices inside that
window: a deployment with no feed at all, or a feed for a different quarter,
cannot say that a record is missing. Without that guard the signal would fire on
every high-value invoice the system ever sees — the difference between a signal
and a false-positive generator.

**The movement-record source is simulated.** No live e-Way Bill feed is connected.
`ingestion/samples/eway_movement_sample.csv` stands in for one; it deliberately omits
some references and understates one, so the signal is neither silent nor universal.
A production deployment would replace the CSV with a real feed and keep the same
node type and join.

**`:GSTINFiling`**
| Property | Type | Notes |
|---|---|---|
| `id` | string (UUID) | |
| `period` | string | e.g. "2026-Q1" |
| `return_type` | string | GSTR-1 / GSTR-3B |
| `filed_on` | date, nullable | null = not filed |
| `reconciliation_status` | string | matched / mismatched / pending |

### 2.2 Relationship Types

| Relationship | From → To | Key properties |
|---|---|---|
| `:DIRECTOR_OF` | `Director` → `Company` | `appointed_date`, `resigned_date` (nullable) |
| `:REGISTERED_AT` | `Company` → `Address` | `since_date` |
| `:OPERATES_ACCOUNT` | `Company` → `BankAccount` | `since_date` |
| `:ISSUED_INVOICE_TO` | `Company` → `Company` | links via intermediate `:Transaction` node — modeled as `(Company)-[:BILLED]->(Transaction)-[:BILLED_TO]->(Company)` for richer queryability |
| `:BILLED` / `:BILLED_TO` | `Company` ↔ `Transaction` | direction of invoice flow |
| `:FILED_RETURN` | `Company` → `GSTINFiling` | |
| `:RESOLVED_AS` | `Company`/`Director` → canonical entity node | `confidence` (float), `method` (deterministic/fuzzy), written by entity-resolution job |
| `:MEMBER_OF_CYCLE` | `Company` → synthetic `:FraudCycle` node (see §2.3) | `hop_position` |
| `:MEMBER_OF_COMMUNITY` | `Company` → synthetic `:FraudCommunity` node | |

### 2.3 Derived / Analytical Nodes

To keep detected patterns queryable and explainable rather than recomputed ad hoc every time, structural analytics jobs materialize their findings as first-class nodes:

**`:FraudCycle`** — `{id, hop_count, total_amount, detected_at, algorithm_version}`
**`:FraudCommunity`** — `{id, member_count, internal_density, external_degree_ratio, detected_at}`

This lets the API answer "why was this entity flagged" (§TRD 4.6) by simply traversing `Company -[:MEMBER_OF_CYCLE]-> FraudCycle <-[:MEMBER_OF_CYCLE]- Company` rather than re-running graph algorithms per request.

### 2.4 Indexes & Constraints

Base constraints and indexes live in `graph/cypher/constraints.cypher` and
`graph/cypher/indexes.cypher`. Schema changes are added as **numbered migration
files** in `graph/cypher/migrations/`, applied in filename order by
`api/benchmarks/apply_schema.py`; a migration is never edited once applied.

```cypher
CREATE CONSTRAINT company_cin IF NOT EXISTS FOR (c:Company) REQUIRE c.cin IS UNIQUE;
CREATE CONSTRAINT company_gstin IF NOT EXISTS FOR (c:Company) REQUIRE c.gstin IS UNIQUE;
CREATE CONSTRAINT director_din IF NOT EXISTS FOR (d:Director) REQUIRE d.din IS UNIQUE;
CREATE INDEX company_name_idx IF NOT EXISTS FOR (c:Company) ON (c.name);
CREATE INDEX address_normalized_idx IF NOT EXISTS FOR (a:Address) ON (a.normalized_address);
CREATE INDEX bank_ifsc_idx IF NOT EXISTS FOR (b:BankAccount) ON (b.ifsc, b.account_hash);
CREATE INDEX company_risk_score_idx IF NOT EXISTS FOR (c:Company) ON (c.risk_score);
```

Migration `001_eway_bill_movement.cypher` adds the movement-record source's key and
the lookup index the join depends on:

```cypher
CREATE CONSTRAINT eway_bill_movement_ref IF NOT EXISTS
FOR (m:EWayBillMovement) REQUIRE m.ref IS UNIQUE;
CREATE INDEX transaction_eway_bill_ref IF NOT EXISTS
FOR (t:Transaction) ON (t.eway_bill_ref);
```

Migration `002_eway_bill_movement_source.cypher` adds the singleton source's key:

```cypher
CREATE CONSTRAINT eway_bill_movement_source_id IF NOT EXISTS
FOR (s:EWayBillMovementSource) REQUIRE s.id IS UNIQUE;
```

## 3. PostgreSQL Schema (Application Layer)

```sql
-- Users of the internal tool (officers/auditors)
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('officer','auditor','analyst','admin')),
    created_at    TIMESTAMPTZ DEFAULT now(),
    -- Bumped whenever the password changes. Access tokens carry the version
    -- they were minted with, so a bump ends every session the old password
    -- had (TASK C1).
    token_version INTEGER NOT NULL DEFAULT 1
);

-- Refresh tokens: opaque random strings, stored only as a SHA-256 digest, so
-- a database dump cannot be replayed as a login. Revocation is server-side —
-- "log out" really ends the session (TASK C1).
CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    issued_at   TIMESTAMPTZ DEFAULT now(),
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked_at  TIMESTAMPTZ,
    replaced_by UUID REFERENCES refresh_tokens(id) ON DELETE SET NULL,
    client_ip   TEXT,
    user_agent  TEXT
);

-- Login attempts. The rate limiter and the lockout read from here, so the
-- decision survives an API restart and can be audited afterwards (TASK C1).
CREATE TABLE login_attempts (
    id         BIGSERIAL PRIMARY KEY,
    email      TEXT NOT NULL,
    client_ip  TEXT NOT NULL,
    succeeded  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Which migration files have been applied. The Postgres schema is created by
-- docker-entrypoint-initdb.d, which only runs on the FIRST start of an empty
-- volume, so a new migration file would otherwise be silently ignored by an
-- existing stack (TASK C1 — see scripts/apply_migrations.sh).
CREATE TABLE schema_migrations (
    name       TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Case files opened against a flagged entity/ring
CREATE TABLE cases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_ref      TEXT NOT NULL,          -- Company.id or FraudCycle.id in Neo4j
    entity_type     TEXT NOT NULL CHECK (entity_type IN ('company','cycle','community')),
    opened_by       UUID REFERENCES users(id),
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','under_review','escalated','closed')),
    risk_score_snapshot NUMERIC,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Exported evidence bundles for a case
CREATE TABLE case_exports (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id     UUID REFERENCES cases(id) ON DELETE CASCADE,
    format      TEXT NOT NULL CHECK (format IN ('json','pdf')),
    file_path   TEXT NOT NULL,
    exported_by UUID REFERENCES users(id),
    exported_at TIMESTAMPTZ DEFAULT now()
);

-- Ingestion job tracking (CSV bulk loads and PDF agentic parses)
CREATE TABLE ingestion_jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_type      TEXT NOT NULL CHECK (job_type IN ('csv','pdf')),
    source_file   TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','success','partial_success','failed')),
    rows_ingested INTEGER DEFAULT 0,
    rows_failed   INTEGER DEFAULT 0,
    error_log     JSONB,
    started_at    TIMESTAMPTZ,
    completed_at  TIMESTAMPTZ,
    created_by    UUID REFERENCES users(id)
);

-- Audit trail — every view/export of a case, for accountability
CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    action      TEXT NOT NULL,        -- e.g. 'viewed_entity', 'exported_case', 'ran_ingestion'
    target_ref  TEXT,                 -- entity id / case id being acted on
    metadata    JSONB,
    occurred_at TIMESTAMPTZ DEFAULT now()
);

-- Model registry — which GNN checkpoint produced which scores (for reproducibility)
CREATE TABLE model_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_tag     TEXT NOT NULL,     -- e.g. 'graphsage-v1.2-amlworld'
    trained_on      TEXT NOT NULL,     -- dataset description
    metrics         JSONB,             -- F1, AUC-PR, recall@k at training time
    checkpoint_path TEXT NOT NULL,
    deployed_at     TIMESTAMPTZ,
    is_active        BOOLEAN DEFAULT false
);
```

## 4. Data Flow Between Stores

- **Neo4j is authoritative** for anything graph-shaped: entities, relationships, risk scores, cycles, communities.
- **PostgreSQL is authoritative** for anything workflow/process-shaped: who looked at what, case status, export history, ingestion job status, which model version is currently live.
- The FastAPI layer joins the two at the API boundary — e.g., `/api/cases/:id` reads case metadata from Postgres and the live risk score/subgraph from Neo4j in the same response, never duplicating graph data into Postgres.

## 5. Schema Evolution Notes

- Schema changes are added as **new numbered files** in `graph/cypher/migrations/`
  (`001_*.cypher`, `002_*.cypher`, …). An applied migration is never edited — a
  correction goes in a new file. `api/benchmarks/apply_schema.py` applies the base
  constraints/indexes first and then the migrations in filename order; every
  statement is `IF NOT EXISTS`, so re-running is a no-op.
- `risk_score`, `community_id`, `pagerank`, `betweenness` on `:Company` are **write-back fields** populated by scheduled/offline jobs (structural analytics + GNN inference), not computed at read time — keeps API latency low (see TRD §6 performance targets).
- `:FraudCycle` / `:FraudCommunity` nodes are versioned by `algorithm_version` / `detected_at` so re-running analytics after a schema or algorithm change doesn't silently overwrite prior evidence used in an open case.
- `:EWayBillMovement` nodes are **append-only evidence**: a movement record for a given `ref` describes what moved and when. Replacing one silently would change what the signal says about invoices already in a case, so a corrected movement record is a new node with the same `ref` only if the old one is removed in the same transaction.
