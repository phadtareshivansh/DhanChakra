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
1. Open the **Explain** slide-in drawer (from any risk badge). It shows the
   score, a **mini-subgraph of just the evidence** (the invoice loop), the
   2–3 line plain-language reason, and a **View full network** link.
2. Read the **Risk decomposition** — cycle membership, shared director,
   shared address, degree, PageRank, betweenness. Each number is the actual
   contribution of that signal to the heuristic score (feature attribution),
   and a `View full network` link jumps back to the canvas.
3. The explanation is **structural evidence** (subgraph attribution from the
   detected cycle / community / shared links), labelled `method =
   "subgraph_attribution"` in the API — it is **not** learned GNNExplainer.
4. **Network** tab: inspect the transaction graph (invoice edges
   `BILLED`/`BILLED_TO` as in the schema). Cycle edges are surfaced for the
   relevant path set.

## 4. Structural analytics
- **Analytics → Loops**: browse closed invoice loops (min length 3 by default).
  "Hops" correspond to invoice steps; the UI mirrors `MAX_CYCLE_HOPS`.

  The demo dataset contains exactly **one** flagged fraud ring — the six
  **Maya** companies, wired into a closed **6-hop** invoice loop (6 companies):

  | Company | CIN | GSTIN |
  |---|---|---|
  | Maya Infra Projects Pvt Ltd | L12345MH2023PLC900001 | 27HEROA0000A1Z1 |
  | Maya Trading Co Pvt Ltd | L12345MH2023PLC900002 | 27HEROA0000B2Z2 |
  | Maya Logistics Pvt Ltd | L12345MH2023PLC900003 | 27HEROA0000C3Z3 |
  | Maya Exports Pvt Ltd | L12345MH2023PLC900004 | 27HEROA0000D4Z4 |
  | Maya Chemicals Pvt Ltd | L12345MH2023PLC900005 | 27HEROA0000E5Z5 |
  | Maya Steel Pvt Ltd | L12345MH2023PLC900006 | 27HEROA0000F6Z6 |

  Loop shape: `Infra → Trading → Logistics → Exports → Chemicals → Steel → Infra`
  (invoices `INV-HERO-001..006`). `/analytics/loops` reports **hop_count = 6**
  (one hop = one invoice edge) and **total_invoice_amount = ₹5,300,000**. The
  companies keep a low paid-up capital (₹100,000) against these disproportionate
  invoices, so the GNN scores all six at **100.0** (`risk_source = gnn_v1`).

  Three directors each sit on **two** ring companies (three shared-director
  pairs for entity resolution to catch):
  - Rakesh Malhotra — Maya Infra Projects ↔ Maya Trading Co
  - Sunita Rao — Maya Logistics ↔ Maya Exports
  - Deepak Nair — Maya Chemicals ↔ Maya Steel

  Two registered addresses are each shared by **three** companies:
  - 12 Vasant Vihar Lane — Infra, Trading, Logistics
  - 45 Sector 9 Industrial Area — Exports, Chemicals, Steel

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
