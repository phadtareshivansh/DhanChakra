# Implementation Plan
## Dhan-Chakra — Graph-AI Engine for Shell Company Loops & GST Fraud Detection

**Version:** 1.0 | **Companion to:** all prior docs (PRD, TRD, UI/UX, App Flow, Backend Schema)

---

## 1. Team Roles (Suggested — adapt to actual team size)

| Role | Responsibilities |
|---|---|
| Graph/Backend Engineer | Neo4j schema, Cypher/GDS algorithms, FastAPI endpoints |
| ML Engineer | PyTorch Geometric GNN, training on synthetic benchmarks, explainability |
| Frontend Engineer | React + D3.js UI, per UI/UX Design + App Flow docs |
| Data/Ingestion Engineer | CSV/data pipeline, entity resolution, (stretch) agentic PDF ingestion |
| Product Lead | Demo script, PRD alignment, demo-facing narrative, PostgreSQL app-layer schema |

*(In a 4-person team, ML and Data/Ingestion can merge; in a 5–6 person team, split as above.)*

## 2. Phased Build Roadmap

| Phase | Hours | Focus | Deliverable | Owner |
|---|---|---|---|---|
| **0. Setup** | 0–4 | Docker Compose (Neo4j + Postgres + FastAPI + React skeleton); load a small sample of MCA data + one AMLworld synthetic slice | Running stack, seed data loaded | Backend + Data |
| **1. Structural MVP** | 4–16 | NetworkX prototype validated on sample data → promoted to Neo4j Cypher/GDS (WCC, Louvain, cycle detection, centrality); basic FastAPI endpoints (`/entities/search`, `/entities/:id/network`) | Live demo: paste a company, see its community + any detected loop | Backend/Graph |
| **2. Entity Resolution** | 16–24 | Deterministic + fuzzy resolution rules (DIN/address/bank match) → `:RESOLVED_AS` edges | Demo: two differently-named shells collapse into one resolved ring | Data/Ingestion |
| **3. GNN Layer** | 24–36 | GraphSAGE in PyG, pretrained on AMLworld/AMLSim, fine-tuned with structural weak labels; `/entities/:id` returns `risk_score` | Demo: continuous risk score per entity, ranked worklist populated | ML |
| **4. Visualization & Explainability** | 36–44 | D3.js force-directed network view (per UI/UX spec); GNNExplainer wired to `/entities/:id/explain`; Explainability drawer in frontend | Demo: click a flagged node → see the exact loop/pattern that triggered it | Frontend + ML |
| **5. Agentic Ingestion (stretch)** | 44–48 | Llama-3 agent parses a small curated MCA filing PDF sample → new nodes with confidence scores; `/ingest` UI | Demo: unstructured filing → new graph nodes automatically | Data/Ingestion |
| **6. Demo readiness** | Final hours | Case export view, dashboard stat tiles, demo script rehearsal, architecture slide | Demo-ready end-to-end walkthrough (≤ 3 min per PRD §3) | Product |

**Sequencing rationale (unchanged from the earlier research report, restated here as a build commitment):** Phases 1–2 are pure graph-algorithm work with zero ML training risk, so the team always has a working, explainable demo even if Phase 3 (GNN) or Phase 5 (agentic ingestion) run out of time — both are additive, never blocking, per PRD non-functional requirement on reliability.

## 3. Detailed Task Breakdown Per Phase

### Phase 0 — Setup
- [x] `docker-compose.yml`: Neo4j, PostgreSQL, FastAPI (with hot-reload), React (Vite dev server).
- [x] Load Neo4j constraints/indexes from `05_Backend_Schema.md` §2.4.
- [x] Run Postgres migrations from `05_Backend_Schema.md` §3.
- [x] Download/prepare one small IBM AMLworld or AMLSim slice + a sample MCA CSV extract; write a loader script mapping both into the graph schema. (AMLsim-style synthetic benchmark in `api/app/services/gnn/synthetic.py`; MCA/GST loader `ingestion/scripts/load_sample.py`)

### Phase 1 — Structural MVP
- [x] NetworkX prototype notebook: `simple_cycles`, `connected_components`, `louvain_communities`, `betweenness_centrality` on the seed data.
- [x] Port validated logic into Cypher/GDS calls (`gds.wcc.stream`, `gds.louvain.stream`, cycle Cypher pattern from TRD §4.1).
- [x] Materialize `:FraudCycle` / `:FraudCommunity` nodes per Backend Schema §2.3.
- [x] FastAPI: `/api/entities/search`, `/api/entities/{id}`, `/api/entities/{id}/network`.
- [x] Minimal frontend: search box + raw JSON/graph preview (styling comes in Phase 4).

### Phase 2 — Entity Resolution
- [x] Deterministic matcher: exact DIN, exact bank IFSC+account_hash, exact normalized address.
- [x] Fuzzy matcher: name similarity (Jaro-Winkler) + partial overlap, confidence-scored.
- [x] Write `:RESOLVED_AS` edges; expose resolved-cluster view in `/api/entities/{id}/network`.
- [x] Unit tests against a hand-crafted set of "obviously same entity, different name" fixtures.

### Phase 3 — GNN Layer
- [x] Data prep: export node features (attributes + structural features from Phase 1) into PyG `Data`/`HeteroData` objects.
- [x] Train GraphSAGE (2–3 layers) on AMLworld/AMLSim split; log F1/AUC-PR/recall@k per TRD §9.
- [x] Fine-tune / domain-adapt using structural weak labels on the India-shaped graph.
- [x] Persist checkpoint; register in `model_versions` table (Backend Schema §3); load at API startup.
- [x] FastAPI: risk score written back to `Company.risk_score`; `/api/worklist` endpoint (sortable/filterable/paginated).

### Phase 4 — Visualization & Explainability
- [x] Build the design system tokens (colors/typography/spacing from `03_UIUX_Design.md`) as a Tailwind config.
- [x] D3.js force-directed component: node/edge styling, cycle-edge highlighting, zoom/pan, "Fit to view".
- [x] Explainability drawer component; wire to `GNNExplainer`-backed `/api/entities/{id}/explain`.
- [x] Worklist table (dense, filterable) and Dashboard stat tiles per App Flow Journey A.
- [x] Full click-path QA against App Flow §2 Journeys A–C.

### Phase 5 — Agentic Ingestion (stretch, time-boxed — do not let it block Phase 6)
- [x] Curate a small (5–10 document) sample set of MCA-style filing PDFs. (`ingestion/samples/filings/`, generated by `ingestion/scripts/make_sample_filings.py`)
- [x] Build the tool-using extraction agent: prompt + schema for `{director_name, DIN, registered_address, shareholding}` with a confidence score per field. (`api/app/services/agentic_ingest.py` — rules backend default, optional OpenAI-compatible LLM backend)
- [x] Route low-confidence extractions to a manual-confirm UI step (per App Flow Journey D) rather than auto-committing. (amber "needs review" fields + confirm endpoint in `Ingest.tsx` / `/api/v1/ingest/document/confirm`)
- [x] Feature-flag this module in config so its absence doesn't break the rest of the demo if unfinished. (`AGENT_INGEST_BACKEND`, additive module; tests: `test_agentic_ingest.py`)

### Phase 6 — Demo readiness
- [x] Case export view (light-mode, print-ready) — `/api/cases/{id}/export`.
- [x] Seed a "hero" fraud ring in the demo data that reliably produces a clean, visually compelling cycle + explanation (do not rely purely on random synthetic data for the live demo). (Orbit → Harbor → Summit ₹500K loop, GNN ~100, `Demo_Script.md`)
- [x] Rehearse the Journey C script end-to-end, timed to stay under 3 minutes. (`files/Demo_Script.md`)
- [x] One architecture slide summarizing the pipeline (reuse the diagram from `02_TRD.md` §1). (`files/Architecture_Diagram.md`)

## 4. Definition of Done (per phase)

A phase is considered "done enough to move on" when:
1. Its FastAPI endpoint(s) return correct data on the seed dataset (verified manually or via a quick script).
2. The corresponding PRD user story (§6) can be walked through, even if the UI is still rough.
3. Nothing in the phase requires a not-yet-built later phase to function (structural layer never depends on the GNN; GNN never depends on agentic ingestion).

## 5. Milestone Checkpoints (Review check-ins)

| Checkpoint | Expected state |
|---|---|
| Mid-point review | Phases 0–2 complete: graph loaded, cycles/communities visibly detected, entity resolution working |
| Pre-final review | Phases 3–4 complete: GNN risk scores live, network visualization + explainability working end-to-end |
| Final review | Phase 6 complete: full Journey C walkthrough rehearsed and timed |

## 6. Immediate Next Steps (start of build)

1. Stand up `docker-compose.yml` and confirm all four services (Neo4j, Postgres, FastAPI, React) boot and can reach each other.
2. Apply the Neo4j constraints/indexes and Postgres migrations from `05_Backend_Schema.md`.
3. Get one synthetic AMLworld/AMLSim slice and one MCA sample CSV loaded end-to-end through a single loader script, so Phase 1 has real data to run cycle detection against on day one.
