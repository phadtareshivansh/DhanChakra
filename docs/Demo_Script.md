# Dhan-Chakra — Timed Demo Script

A minute-by-minute, stage-ready run-through of **Journey C** (see
`04_AppFlow.md`). Facts match `docs/demo.md`; the numbers in this script were
read off the live stack, not assumed.

- **Target:** under **3:00** (PRD success metric). The core path is timings
  0:00–2:40.
- **Presenter:** Super Admin, so the **Users** page is available for the
  optional role beat.
- **Vocabulary:** one **invoice loop** = a closed cycle of `BILLED` /
  `BILLED_TO` edges. In the sample data that loop is **6 hops** long.

> Read this alongside `docs/demo.md`: this file is the *choreography*, `demo.md`
> is the *reference*. If a number here and `demo.md` ever disagree, `demo.md`
> wins and this file should be corrected.

---

## Pre-flight checklist (do before the demo)

- [ ] `make up && make bootstrap` — seeds the curated sample data, runs
      structural analytics, scores the graph with the GNN.
- [ ] Wait for the API to be healthy: `make ps` shows `api` and `frontend` up.
- [ ] Open **http://localhost:5173** in a maximized browser; log in as the Super
      Admin. Read the password from `.env` (`SUPER_ADMIN_PASSWORD`); it is never
      printed anywhere.
- [ ] Confirm the numbers you will quote are live:
      - Worklist sorted by **Risk score (desc)** → six **Maya** companies at
        **100.0** (`risk_source=gnn_v1`).
      - **Loops** (`/loops`) → exactly **one** ring, `length = 6`,
        **₹5,300,000**.
      - Dashboard tiles → **6** flagged entities, **Maharashtra** as top risk
        state.
- [ ] Have the two sample filings open in a file chooser:
      `ingestion/samples/filings/filing_meridian_trade.pdf` (review flow —
      amber fields) and `ingestion/samples/filings/filing_apollo_transport.pdf`
      (all-green instant fallback).
- [ ] Optional "under the hood" tab: **Neo4j Browser** at
      http://localhost:7474.

---

## Script (timed)

### 0:00 — Login and Dashboard (15 s)

1. Log in as the Super Admin. Point at the Dashboard tiles: **6 flagged
   entities**, **1** cycle detected, **Maharashtra** top risk state.
2. **Line:** "Everything on this screen is read from the live graph — nothing is
   hardcoded. The system ships with a **fixed 3-slot role model**: one Super
   Admin and two standard users, and **no sign-up**."

### 0:15 — Worklist: the ranking (25 s)

1. Open **Worklist** (`/worklist`). Sort by **Risk score (desc)**. The top six
   rows are the **Maya** companies, all at **100.0** (`risk_source=gnn_v1`).
2. Scroll to show the two companies **outside** the ring sitting at **0.0**.
3. **Line:** "These scores come from our GraphSAGE model, which scores every
   company in the graph. The six at the top are a single ring; the clean
   companies fall to zero."

### 0:40 — Entity + Explain: the ring and the "why" (45 s)

1. Open the top company → **`/entity/:id/network`** (Entity Detail, Network tab).
   The D3 graph draws the invoice loop with the **cycle edges highlighted**.
2. Click the **risk badge** to open the **Explain** drawer:
   - the score and plain-language **reasons**,
   - a **mini-subgraph of just the evidence** (the loop),
   - the **Risk decomposition** — cycle membership, shared director, shared
     address, degree, PageRank, betweenness — each shown as its actual
     contribution to the score.
3. **Line:** "Structural analytics found the loop and the GNN scored it; this
   drawer is the evidence an officer can actually show — **method =
   `subgraph_attribution`**, structural evidence, not a black box."

> **Honesty beat (if asked during the demo):** open a company *outside* the ring. Its
> `/explain` returns `cycles: []` and no ring evidence — the ring is not smeared
> across the dataset.

### 1:25 — Loops: the whole ring at once (20 s)

1. Open **Loops** (`/loops`). One ring: the six Maya companies.
2. Point at the shape `Infra → Trading → Logistics → Exports → Chemicals → Steel
   → Infra` (invoices `INV-HERO-001..006`, 2024-01-10 → 2024-01-20), `length = 6`
   and **₹5,300,000**.
3. **Line:** "This is the complete ring in one view — 6 hops, ₹53 lakh of
   circular invoicing. Three directors each sit on two ring companies, and two
   addresses are each shared by three — the structural fingerprints of a shell
   ring."

### 1:45 — Agentic document ingestion (40 s)

1. Open **Ingest** (`/ingest`) → **Document (PDF) — agentic extraction**.
2. Upload `filing_meridian_trade.pdf` → extract with the agent.
3. The preview shows `{company_name, cin, gstin, registered_address,
   director_name, din, shareholding}` with **per-field confidence**. High
   confidence is green (`ready`); amber fields are **`needs_review`**.
4. Correct/confirm the amber fields → **Confirm & create entities**. It is
   written into the graph as a **Company** with `source=agentic`.
5. **Line:** "Low-confidence fields never auto-commit — the officer confirms
   them. Nothing lands in the graph without a human in the loop."

> The default backend is **`rules`** (deterministic, offline). The optional `llm`
> backend only activates when `AGENT_LLM_URL` / `AGENT_LLM_KEY` are set, and
> degrades to `rules` otherwise.

### 2:25 — Case + export (35 s)

1. Back on a flagged company, **create a case**, attach evidence/marks.
2. Open the case → **`/case/:id/export`** and show the print-ready bundle
   (entity + evidence + subgraph), then export it (JSON/print).
3. **Line:** "One action produces the whole investigation file — the score, the
   evidence subgraph, and the exact transactions that prove the loop."

### 3:00 — Wrap-up (20 s)

1. **Line:** "Ingest → graph → GNN risk → explainability → a case file: the
   pipeline is fully vertical, and every layer is independently testable."
2. *(Optional, only if time)* **Settings → User management** → `/admin/users`:
   "Roles are **fixed** — one admin, two analysts. No request body can change a
   role, and the Super Admin cannot edit or reset itself; standard users get
   **403** on these endpoints."
3. Stop. Take questions.

---

## Timing guardrails

- **Never** run **GNN train** (`POST /analytics/gnn/train`) on stage — it is
  already baked in (`make bootstrap`).
- If the review flow feels slow, upload `filing_apollo_transport.pdf` instead:
  all-green, instant commit.
- If Neo4j was restarted, the GDS in-memory graph re-projects on the first
  analytics call (~2 s). Force it during login, not mid-sentence.
- Keep the **Loops** page pre-loaded in a second tab so the `1:25` beat has no
  navigation wait.

## Fallbacks (per step)

| Step | If it fails | Do this |
|---|---|---|
| 0:00 Dashboard | Tiles empty / spinning | `make bootstrap`, refresh; if still empty, skip the tiles and narrate from the Worklist |
| 0:15 Worklist | Scores missing or all heuristic | `POST /analytics/gnn/predict` (or `make bootstrap`). If no GNN checkpoint exists, say so and continue — **heuristic scores remain valid** |
| 0:15 Worklist | Empty list | `make bootstrap` to reload the sample dataset |
| 0:40 Network/Explain | Graph canvas blank | Refresh; use the **Explain** drawer alone (mini-subgraph). If the drawer fails, open `/analytics/loops/{cin}` in a tab and read the cycle evidence |
| 1:25 Loops | No ring listed | `POST /analytics/structural` (or `make bootstrap`), reload `/loops` |
| 1:45 Ingestion | Extraction errors or times out | Switch to `filing_apollo_transport.pdf` (all-green). If the agent still fails, narrate the CSV path (**Ingest → Structured data**) as the deterministic fallback |
| 1:45 Ingestion | `llm` backend unreachable | Expected — it degrades to `rules` automatically; just proceed |
| 2:25 Export | Export/preview error | Show the **case detail** page (entities + evidence) and describe the bundle format |
| Any point | Frontend not loading | `make ps` to check services, `make logs` for errors, then `make restart` |
| Any point | Locked out of login | Read the credentials from `.env`. **Do not** re-run `make env` during the demo — it rewrites passwords |

## Recovery / reset

- `make reset` stops the stack and **deletes all data volumes** (destructive).
- `make up && make bootstrap` returns you to the known demo state.
- `<details><summary>Forgot the Super Admin password?</summary>`

  There is no UI or API for this by design. Run the break-glass CLI on the host:

  ```bash
  docker compose exec api python /scripts/reset_super_admin.py --dry-run   # preview
  docker compose exec api python /scripts/reset_super_admin.py            # apply
  ```

  It reads `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASSWORD` from the environment and
  updates the existing admin row in place. See the README's **Account recovery**
  section for flags and exit codes.

  </details>

## Links

- Reference flow and facts: `docs/demo.md`
- Journey C definition: `04_AppFlow.md`
- Architecture: `02_TRD.md` §1 / `Architecture_Diagram.md`
- Sample data: `ingestion/samples/`
