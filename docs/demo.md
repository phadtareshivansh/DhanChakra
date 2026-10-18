# Dhan-Chakra — Demo Flow (AppFlow Journey A–D)

A 3–5 minute run-through for judges. The bootstrap already loaded the curated sample data.

## 1. Login
- Visit http://localhost:5173
- Demo credentials:
  - **Officer (Admin):** officer@dggi.gov.in / officer123
  - **Analyst:** analyst@dggi.gov.in / analyst123
- (If you used `scripts/init_env.py`, the passwords were newly generated.)

## 2. Worklist — see what the system flags
1. Go to **Worklist**.
2. Check the risk bands (Critical ≥85, High 65–84, Medium ≥40). The loaded
   dataset should surface several risky entities.
3. Sort by **Risk Score (desc)** and open the highest-risk company.

## 3. Entity Detail — explainability first
1. Read the **Risk decomposition** (cycles, director/address links, degree,
   pagerank, betweenness) — each number is explicitly attributed.
2. **Explain** panel: see the exact Cypher/logic trace that drove the score.
3. **Network** tab: inspect the transaction graph (invoice edges
   `BILLED`/`BILLED_TO` as in the schema). Cycle edges are surfaced for the
   relevant path set.

## 4. Structural analytics
- **Analytics → Loops**: browse closed invoice loops (min length 3 by default).
  "Hops" correspond to invoice steps; the UI mirrors `MAX_CYCLE_HOPS`.
- **Analytics → Structural** (if called): cycles, communities, centrality,
  heuristic risk, and entity resolution all run together. The Makefile's
  `bootstrap` and `test-all` both do this.

## 5. Document ingestion (the "needs review" flow)
1. **Ingest → Upload PDF**. Try one of the five sample filings:
   - `ingestion/samples/filings/filing_apollo_transport.pdf`
2. The API extracts fields via the rules extractor (backend `rules`),
   returning a `needs_review`/`ready` status and per-field confidence.
3. **Confirm** the extracted values — the result is written as a **Company**
   (with `source: agentic`) and related nodes. The test suite's
   `test_live_document_flow` exercises this end-to-end (and cleans up).

## 6. CSV ingestion (optional)
- **Ingest → Upload CSV**: the route accepts MCA/GST-like CSVs; on partial
  failures it marks the job `partial_success` and lists failed rows.

## 7. Cases & audit
- Create/open a **Case** for a flagged entity, attach evidence, and
  **Export** a print-ready bundle.
- Check the **Audit log** (includes `ran_structural_analytics`,
  `ran_entity_resolution`, `ran_gnn_predict`, `exported_case`, logins, etc).

## Quick reset
- `make reset` removes all data volumes and rebuilds from a clean DB.
- After `make reset && make up && make bootstrap`, you're back to the
  known demo state.
