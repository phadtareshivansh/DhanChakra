# Technical Requirement Document (TRD)
## Dhan-Chakra — Graph-AI Engine for Shell Company Loops & GST Fraud Detection

**Version:** 1.0 | **Companion to:** 01_PRD.md, 05_Backend_Schema.md

---

## 1. System Overview

Dhan-Chakra is a layered pipeline: **Ingestion → Graph Construction → Structural Analytics → Learned Risk Scoring → Explainability → API → Web UI**. Each layer is independently testable and demoable, per the phased build strategy.

```
┌────────────┐   ┌──────────────┐   ┌────────────────┐   ┌────────────────┐   ┌───────────────┐   ┌────────────┐
│  Ingestion │──▶│    Neo4j      │──▶│  Structural     │──▶│  GNN Risk       │──▶│  Explainability│──▶│  FastAPI    │──▶ React/D3 Web UI
│  (CSV/API/ │   │  Property     │   │  Analytics       │   │  Scoring        │   │  (GNNExplainer)│   │  Layer      │
│  LLM PDF)  │   │  Graph        │   │  (GDS: WCC,      │   │  (PyTorch       │   │                │   │             │
│            │   │               │   │  Louvain, cycles,│   │  Geometric:     │   │                │   │             │
│            │   │               │   │  centrality)     │   │  GraphSAGE/GAT) │   │                │   │             │
└────────────┘   └──────────────┘   └────────────────┘   └────────────────┘   └───────────────┘   └────────────┘
```

## 2. Technology Stack

| Layer | Technology | Version (target) | Notes |
|---|---|---|---|
| Graph database | Neo4j Community + Graph Data Science (GDS) library | Neo4j 5.x, GDS 2.x | WCC, Louvain/Leiden, PageRank, betweenness, Cypher variable-length cycle queries |
| Prototyping | Python + NetworkX | Python 3.11, NetworkX 3.x | Day-1 in-memory validation before promoting to Cypher |
| GNN modeling | PyTorch + PyTorch Geometric (PyG) | PyTorch 2.x, PyG 2.5+ | GraphSAGE, GAT, heterogeneous GNN (HGT/R-GCN) |
| Explainability | PyG `GNNExplainer` / `CaptumExplainer` | PyG built-in | Attaches minimal supporting subgraph per prediction |
| Document ingestion | Llama-3 70B (API) or quantized local equivalent, tool-using agent | — | Extracts director/address/DIN entities from MCA PDFs |
| Backend API | FastAPI | 0.11x | Serves graph queries, model inference, worklist, export |
| Backend runtime | Uvicorn/Gunicorn | — | ASGI server |
| Metadata store | PostgreSQL | 15/16 | Users, audit trail, worklist status, case exports (see Backend Schema) |
| Frontend | React (Vite) + TypeScript | React 18 | SPA consuming FastAPI |
| Graph visualization | D3.js (force-directed) | D3 v7 | Interactive network rendering, click-to-explore |
| Styling | Tailwind CSS | 3.x | Utility-first, matches design system in 03_UIUX_Design.md |
| Containerization | Docker + Docker Compose | — | One-command local demo bring-up |
| Data validation | Pydantic | v2 | API request/response schema validation |

## 3. Data Sources

| Source | Purpose | Notes |
|---|---|---|
| MCA Company Master Data (data.gov.in / OGD) | Real company/director/address schema and seed records | Public bulk CSV/API; no scraping of live portal beyond terms |
| IBM AMLworld / AMLSim | Synthetic transaction graph with ground-truth laundering typologies (fan-in, fan-out, cycle, scatter-gather, etc.) | Used to pretrain and stress-test the GNN |
| Elliptic / IEEE-CIS (secondary) | Cross-domain validation of pipeline generalization | Optional, time-permitting |
| Curated sample MCA filing PDFs | Agentic ingestion demo | Small, bounded set — not open-ended scraping |

All identity fields (PAN, Aadhaar-linked data) are masked/hashed or entirely synthetic — see PRD §9 (Assumptions) and §NFR (Privacy).

## 4. Core Algorithms — Technical Spec

### 4.1 Cycle Detection
- **Primary:** Cypher variable-length pattern match:
  `MATCH p = (c:Company)-[:ISSUED_INVOICE_TO*3..8]->(c) RETURN p`
- **At scale:** Pre-filter via WCC to shrink search space, then apply Johnson's algorithm (`networkx.simple_cycles`) or Neo4j GDS path-finding procedures on each component.
- **Output:** list of `(cycle_id, [company_ids], total_invoice_amount, hop_count)`.

### 4.2 Community Detection (Fraud Islands)
- **Pipeline:** `WCC` (coarse clustering) → `Louvain` or `Leiden` (fine clustering within large components).
- **Flagging rule:** community with internal edge density above threshold θ₁ and external degree ratio below θ₂, member count in a configurable "shell-ring" size band.
- **GDS calls:** `gds.wcc.stream`, `gds.louvain.stream` / `gds.leiden.stream`.

### 4.3 Centrality Features
- `gds.pageRank.stream`, `gds.betweenness.stream`, `gds.degree.stream` computed per entity and written back as node properties for downstream GNN feature input.

### 4.4 Entity Resolution
- **Deterministic pass:** exact match on DIN, bank IFSC+account, normalized registered address string.
- **Fuzzy pass:** name similarity (Levenshtein/Jaro-Winkler) + partial address/phone/email overlap, threshold-gated, human-reviewable before merge.
- **Output:** `RESOLVED_AS` edges linking synthetic identities to a canonical entity node before GNN feature extraction.

### 4.5 GNN Risk Scoring
- **Architecture:** 2–3 layer GraphSAGE (mean/pool aggregator) as base; optional GAT/heterogeneous (HGT/R-GCN) upgrade for attention over relation types.
- **Input features per node:** entity attributes (turnover, filing age, sector/NIC code) + structural features from §4.3 (PageRank, betweenness, degree, community id).
- **Training labels:** synthetic ground truth from AMLworld/AMLSim (primary) + weak/silver labels from §4.1–4.2 structural flags (secondary, for domain adaptation to the India-shaped graph).
- **Class imbalance handling:** class-weighted or focal loss; SMOTE-style oversampling on embeddings if needed.
- **Output:** per-entity fraud probability (0–1), exposed as a 0–100 risk score.

### 4.6 Explainability
- `GNNExplainer` (or PyG's generic `Explainer` API) run on-demand for any entity above the score threshold, returning the minimal edge/node subset that most influenced the prediction. This subgraph is what the UI highlights.

### 4.7 Agentic Document Ingestion (Stretch)
- Tool-using LLM agent (Llama-3-class) parses a curated MCA filing PDF, extracts `{director_name, DIN, registered_address, shareholding}`, runs entity-resolution rules (§4.4) against existing graph nodes, and either creates new nodes or links to existing ones. Confidence score attached to every extracted field; low-confidence extractions are queued for manual review rather than auto-committed.

## 5. API Specification (FastAPI) — Core Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/entities/search?q=` | Search company/GSTIN/CIN/name |
| `GET` | `/api/entities/{id}` | Entity detail: attributes, risk score, community id |
| `GET` | `/api/entities/{id}/network?depth=` | Subgraph (nodes+edges) around an entity for D3 rendering |
| `GET` | `/api/entities/{id}/explain` | Evidence subgraph + natural-language reason for the flag |
| `GET` | `/api/worklist?sort=&filter=&page=` | Ranked, filterable, paginated risk worklist |
| `POST` | `/api/cases/{id}/export` | Export a case bundle (JSON/PDF) with subgraph + score + evidence |
| `POST` | `/api/ingest/csv` | Bulk-load structured data into the graph (admin/demo use) |
| `POST` | `/api/ingest/document` | Submit a PDF filing to the agentic ingestion pipeline |
| `GET` | `/api/stats/overview` | Aggregate dashboard stats (entities scanned, flagged count, top sectors/states) |
| `GET` | `/health` | Liveness/readiness probe |

All responses are Pydantic-validated JSON; error responses follow a consistent `{code, message, details}` envelope.

## 6. Performance Requirements

| Operation | Target |
|---|---|
| Entity search | < 300ms (indexed lookup) |
| Cycle detection on a component ≤ 50K nodes | < 5s |
| WCC + Louvain on full demo graph (≤ 500K nodes) | < 10s |
| GNN inference (single entity, on-demand) | < 1s |
| Explainability subgraph generation | < 2s |
| Worklist page load (paginated, 50/page) | < 500ms |

Latency numbers are reported per tested graph size in the demo — no unqualified "milliseconds at any scale" claims (see prior research report §8).

## 7. Security & Privacy Requirements

- No real PAN/Aadhaar numbers ingested; identity fields masked/hashed or synthetic.
- API access gated behind a basic auth/token layer for the demo (production-grade RBAC out of scope for v1).
- All exported case bundles are scoped to what a human reviewer explicitly requested — no bulk unauthenticated export endpoint.
- Input validation on all ingestion endpoints (Pydantic schemas) to prevent malformed data from corrupting the graph.

## 8. Infrastructure & Deployment

- **Local/demo:** `docker-compose up` bringing up Neo4j, PostgreSQL, FastAPI backend, and the React frontend as separate services on a shared network.
- **Environments:** `.env`-driven config for DB URIs, model checkpoint paths, and feature-flagging the agentic ingestion module (so the demo degrades gracefully if that stretch goal isn't finished).
- **Model artifacts:** trained GraphSAGE/GAT checkpoint stored under `/models` and loaded at API startup; retraining is a separate offline script, not part of the live request path.

## 9. Testing Requirements

| Layer | Test type |
|---|---|
| Structural algorithms | Unit tests against a small hand-crafted graph with known planted cycles/communities |
| GNN | Evaluation on held-out synthetic AMLworld/AMLSim split — F1, AUC-PR, recall-at-k (see PRD success metrics) |
| Explainability | Spot-check that returned subgraphs contain the planted fraud motif |
| API | Integration tests per endpoint (happy path + validation errors) |
| Frontend | Manual QA checklist per user story in PRD §6, plus smoke test of the full demo flow before a release |

## 10. Dependencies & Third-Party Services

- Neo4j (self-hosted, Community edition sufficient for demo scale)
- LLM API (for agentic ingestion) — provider chosen at build time based on available credits/access; module is feature-flagged and optional
- No other external paid services required for the core demo path
