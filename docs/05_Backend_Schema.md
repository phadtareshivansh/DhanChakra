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
| `eway_bill_ref` | string, nullable | absence = red flag signal |

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

```cypher
CREATE CONSTRAINT company_cin IF NOT EXISTS FOR (c:Company) REQUIRE c.cin IS UNIQUE;
CREATE CONSTRAINT company_gstin IF NOT EXISTS FOR (c:Company) REQUIRE c.gstin IS UNIQUE;
CREATE CONSTRAINT director_din IF NOT EXISTS FOR (d:Director) REQUIRE d.din IS UNIQUE;
CREATE INDEX company_name_idx IF NOT EXISTS FOR (c:Company) ON (c.name);
CREATE INDEX address_normalized_idx IF NOT EXISTS FOR (a:Address) ON (a.normalized_address);
CREATE INDEX bank_ifsc_idx IF NOT EXISTS FOR (b:BankAccount) ON (b.ifsc, b.account_hash);
CREATE INDEX company_risk_score_idx IF NOT EXISTS FOR (c:Company) ON (c.risk_score);
```

## 3. PostgreSQL Schema (Application Layer)

```sql
-- Users of the internal tool (officers/auditors)
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT UNIQUE NOT NULL,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('officer','auditor','analyst','admin')),
    created_at    TIMESTAMPTZ DEFAULT now()
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

- `risk_score`, `community_id`, `pagerank`, `betweenness` on `:Company` are **write-back fields** populated by scheduled/offline jobs (structural analytics + GNN inference), not computed at read time — keeps API latency low (see TRD §6 performance targets).
- `:FraudCycle` / `:FraudCommunity` nodes are versioned by `algorithm_version` / `detected_at` so re-running analytics after a schema or algorithm change doesn't silently overwrite prior evidence used in an open case.
