# Product Requirement Document (PRD)
## Dhan-Chakra — Graph-AI Engine for Shell Company Loops & GST Fraud Detection

**Version:** 1.0 | **Stage:** Pre-production (v1) | **Owner:** Dhan-Chakra product team

---

## 1. Purpose

Dhan-Chakra gives revenue intelligence officers and forensic auditors a single tool to see, score, and explain circular-trading rings, shell-company networks, and fraudulent ITC claims — replacing manual spreadsheet cross-referencing with an explainable, graph-native risk engine.

## 2. Problem Statement

Fraud rings register multiple shell entities, circulate fabricated invoices between them (A→B→C→A), and claim GST Input Tax Credit against tax that was never deposited. Relational/BI tools inspect transactions in isolation and cannot see multi-hop, cross-state circular patterns. DGGI's own AI-driven analytics drives have already recovered tens of thousands of crores using this class of pattern, confirming both the scale of the problem and the value of graph-native detection.

## 3. Goals & Success Metrics

| Goal | Success Metric |
|---|---|
| Detect circular trading loops of arbitrary length | ≥ 95% recall of planted cycles on synthetic benchmark data |
| Surface shell-company communities | Louvain/Leiden clusters match ≥ 90% of planted fraud rings in AMLworld/AMLSim test sets |
| Reduce manual audit triage time | Ranked worklist cuts "which entity to investigate first" decision to < 30 seconds per case in demo |
| Explainability | 100% of flagged entities ship with a visible supporting subgraph (loop / shared director / burst) |
| Demo readiness | End-to-end flow (upload → graph → score → explain → worklist) runs live in under 3 minutes |

## 4. Target Users / Personas

1. **Revenue Intelligence Officer (primary)** — needs a ranked, explainable worklist of high-risk GSTINs to prioritize audits.
2. **Forensic Auditor (primary)** — needs to visually trace a specific entity's network, export evidence (the loop, shared directors) for a case file.
3. **Compliance/Policy Analyst (secondary)** — needs aggregate views (sector-wise risk, state-wise hotspots) for policy reporting.
4. **Demo/evaluation viewer** — needs a fast, visually compelling, technically credible walkthrough.

## 5. Scope

### 5.1 In Scope (v1)
- Ingest structured company/GSTIN/transaction data (CSV/API) into a graph.
- Structural fraud-ring detection: cycle detection, WCC, Louvain/Leiden community detection, centrality-based risk features.
- Entity resolution: merge shell identities sharing director/address/bank account.
- GNN-based risk scoring (GraphSAGE) trained on public synthetic AML benchmarks + weak labels.
- Explainability layer: every score ships with its supporting subgraph.
- Interactive web UI: entity search, network graph visualization, ranked worklist, case detail view.
- Agentic PDF ingestion for a curated sample of MCA filings (stretch goal, Phase 5).

### 5.2 Out of Scope (v1)
- Real-time streaming ingestion from live GSTN/MCA systems.
- Federated learning across institutions.
- Legal/enforcement workflow integration (case filing, penalty issuance).
- Production-grade authentication/authorization, multi-tenant hosting.
- Mobile app.

## 6. User Stories

| # | As a... | I want to... | So that... |
|---|---|---|---|
| U1 | Revenue Intelligence Officer | see a ranked worklist of the riskiest entities | I know where to focus audit resources first |
| U2 | Auditor | search for a company by GSTIN/CIN/name | I can start an investigation from a known lead |
| U3 | Auditor | see the company's network graph with flagged loops highlighted | I can visually understand the fraud structure |
| U4 | Auditor | click a flagged entity and see *why* it was flagged | I can justify the flag in an audit report |
| U5 | Auditor | see which other companies share a director/address/bank account with a flagged entity | I can trace the full extent of a shell-ring |
| U6 | Officer | filter the worklist by state, sector, or risk score range | I can slice the caseload by jurisdiction or priority |
| U7 | Officer | export a case (subgraph + score + evidence) | I can attach it to a formal audit file |
| U8 | Demo/evaluation viewer | see a live end-to-end walkthrough with real-looking data | I can evaluate technical credibility quickly |

## 7. Functional Requirements

- **FR1** — System shall ingest company, director, address, bank account, invoice/transaction, and GSTIN filing data into a property graph.
- **FR2** — System shall detect cycles of length 3–8 in the invoice/transaction graph and list all companies involved in each cycle.
- **FR3** — System shall compute Weakly Connected Components and Louvain/Leiden communities, and flag communities with high internal density and low external degree.
- **FR4** — System shall compute PageRank, betweenness, and degree centrality per entity as risk features.
- **FR5** — System shall resolve entities sharing a DIN, bank account, or normalized address into a linked cluster.
- **FR6** — System shall produce a continuous fraud-risk score (0–100) per entity via the trained GNN.
- **FR7** — System shall attach an explainable subgraph (the specific loop/relationship/burst) to every risk score above a configurable threshold.
- **FR8** — System shall provide a searchable, filterable, sortable worklist UI ranked by risk score.
- **FR9** — System shall render an interactive force-directed graph for any selected entity, showing its immediate and extended network.
- **FR10** — System shall allow exporting a case (entity + subgraph + score + evidence) as a shareable artifact (JSON/PDF).

## 8. Non-Functional Requirements

| Category | Requirement |
|---|---|
| Performance | Structural queries (cycle detection, community detection) return in < 5s on a graph of ≤ 500K nodes / 5M edges (synthetic demo scale) |
| Explainability | No risk score is shown without an attached evidence subgraph |
| Usability | A first-time user can go from landing page to a flagged fraud ring in ≤ 3 clicks |
| Reliability | Graph-algorithm layer (Phase 1–2) must work standalone even if the GNN/LLM layers fail |
| Privacy | No real PAN/Aadhaar-linked personal data is ingested; demo data uses public MCA fields and synthetic transactions only |
| Portability | Runs locally via Docker Compose for demo; no dependency on live GSTN/MCA production access |

## 9. Assumptions & Constraints

- Real-time GSTN/MCA API access is not available without a licensed GSP or a direct authority agreement; the system uses public MCA bulk data plus public synthetic AML benchmark datasets (IBM AMLworld/AMLSim) shaped to look India-relevant (INR amounts, GSTIN-style IDs).
- No confirmed real fraud labels are available; the GNN is trained on synthetic ground truth and validated against structural heuristics as weak labels.
- The team has v1-scale compute (single GPU or CPU-only fallback) — model size and graph scale are chosen accordingly.

## 10. Risks

| Risk | Mitigation |
|---|---|
| No real labeled data | Pretrain on public synthetic AML benchmarks; use structural flags as weak labels |
| GNN doesn't converge in time | Structural layer (Phase 1–2) is a complete, explainable, standalone demo on its own |
| False positives on legitimate fast-growing SMEs | Always pair score with evidence subgraph; frame as audit-prioritization aid, not verdict |
| Data privacy concerns in demo | Mask/hash all identity fields; use only public MCA fields + synthetic transactions |

## 11. Milestones (aligned to Implementation Plan)

See **06_Implementation_Plan.md** for the detailed phase-by-phase schedule (Setup → Structural MVP → Entity Resolution → GNN Layer → Visualization/Explainability → Agentic Ingestion → Demo readiness).
