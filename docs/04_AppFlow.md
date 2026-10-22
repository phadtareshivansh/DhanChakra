# Application Flow (App Flow)
## Dhan-Chakra — Web Application Navigation & User Journeys

**Version:** 1.0 | **Companion to:** 03_UIUX_Design.md, 05_Backend_Schema.md

---

## 1. Navigation Structure (Sitemap)

```
Dhan-Chakra Web App
│
├── /login                       (auth gate — demo-simple token/basic auth)
│
├── /dashboard                   (Overview: stat tiles, top risks, quick search)
│
├── /worklist                    (Ranked, filterable entity risk table)
│
├── /entity/:id                  (Entity Detail + Network Explorer)
│     ├── overview tab           (attributes, filing history, risk score)
│     ├── network tab            (D3 force-directed graph, default active)
│     └── evidence tab           (explainability panel content, also reachable as a drawer)
│
├── /case/:id/export              (Case export preview — light mode, print-ready)
│
├── /ingest                       (Admin/demo-only: CSV + PDF upload, ingestion status)
│
└── /settings                     (theme toggle, risk-threshold config — demo scope: minimal)
```

## 2. Primary User Journeys

### Journey A — Officer triages the daily worklist (U1, U6)
1. Land on **/dashboard** → see stat tiles (Entities Scanned, Flagged Rings, Est. ITC at Risk, Top Risk State).
2. Click **"View full worklist"** → **/worklist**.
3. Apply filters (state = Maharashtra, risk score ≥ 65) via chip filters.
4. Sort by Risk Score descending.
5. Click the top row → **/entity/:id** (network tab active by default).
6. Scan the highlighted cycle in the graph canvas.
7. Click the entity's risk badge → Explainability drawer slides in with the plain-language reason and evidence subgraph.
8. Click **"Export case"** → **/case/:id/export** → download PDF/JSON.

*Success criterion (PRD §3): steps 1–6 completable in under 3 clicks from dashboard to a visible flagged loop.*

### Journey B — Auditor investigates a known lead (U2, U3, U4, U5)
1. From **any page**, use the global search bar (persistent in top nav) → type a GSTIN/CIN/company name.
2. Select the matching result → **/entity/:id**.
3. Default view: **network tab** — immediate 1-hop neighborhood rendered.
4. Click **"Expand network"** control to pull in 2nd/3rd-hop connections (directors, shared addresses/bank accounts).
5. Cycle edges auto-highlight in red per the design system; hovering a node shows its type + risk badge.
6. Click a shared-director node → side panel lists every other company linked to that director (entity-resolution output).
7. Click **"Why flagged?"** → Explainability drawer.
8. Optionally pin/export this subgraph as evidence.

### Journey C — Demo/evaluation walkthrough (end-to-end flow)
1. **/ingest** — show a small CSV of synthetic entities being loaded live (or pre-loaded, narrated as "this is what ingestion looks like").
2. **/dashboard** — show the stat tiles populate.
3. **/worklist** — sort by risk, point at the top-ranked shell ring.
4. **/entity/:id** network tab — show the cycle rendered and highlighted.
5. Click risk badge → Explainability drawer — this is the "wow" moment proving the system isn't a black box.
6. **/case/:id/export** — show the print-ready evidence bundle.
Total target time: **under 3 minutes**, per PRD success metric.

### Journey D — Ingestion (admin/demo)
1. **/ingest** → choose "Structured data (CSV)" or "Document (PDF)".
2. CSV path: upload → backend validates schema (Pydantic) → shows row count ingested + any validation errors → redirects to updated **/dashboard**.
3. PDF path (stretch goal): upload → agentic parser extracts entities → UI shows extracted fields with a confidence score per field → low-confidence fields flagged for manual confirm before commit to the graph.

## 3. Screen-Level State Transitions

| Screen | Entry states | Key actions | Exit / next screen |
|---|---|---|---|
| Login | Unauthenticated | Submit credentials | → Dashboard |
| Dashboard | Loading → Loaded → (Empty if no data ingested) | Quick search, "View worklist" | → Worklist, → Entity Detail |
| Worklist | Loading → Loaded → Filtered/Sorted → Empty (no matches) | Filter, sort, click row | → Entity Detail |
| Entity Detail | Loading → Loaded (network tab default) | Switch tabs, expand network, open explainability drawer, export | → Case Export, back to Worklist |
| Explainability Drawer (overlay, not a route) | Closed → Open | View evidence, close, "view full network" | Returns to Entity Detail canvas |
| Case Export | Loading → Preview ready | Download PDF/JSON | Stays on page (download action) |
| Ingest | Idle → Uploading → Validating → Success/Error | Upload, confirm low-confidence fields (PDF path) | → Dashboard |

## 4. Global UI Elements (present on every authenticated screen)

- **Top navigation bar:** Dhan-Chakra logo/mark, global search, nav links (Dashboard / Worklist / Ingest / Settings), user menu.
- **Persistent risk-legend key** (small, dismissible): reminds users what each risk color means — supports the "explainability always visible" principle.
- **Breadcrumb** on nested screens (e.g., `Worklist > Entity ABC1234 > Network`).

## 5. Error & Edge-Case Flows

- **No search results:** friendly empty state with a suggestion to broaden the query.
- **Entity has insufficient data for a GNN score:** show `risk-neutral` badge with label "Insufficient data" rather than a misleading default score.
- **Graph too large to render fully:** canvas defaults to 1-hop view with a clear "Expand" affordance rather than silently truncating without indication.
- **Ingestion validation failure:** row-level error list shown inline, partial-success ingestion allowed (valid rows committed, invalid rows reported) rather than all-or-nothing failure.

## 6. Responsive Behavior

- **Desktop (primary target — this is an analyst tool):** full split-view layouts as described.
- **Tablet:** entity detail collapses to stacked (metadata panel above graph canvas, tabs remain).
- **Mobile:** out of scope for v1 (per PRD §5.2); worklist and dashboard degrade to single-column read-only views if accessed, network canvas shows a "best viewed on desktop" notice.
