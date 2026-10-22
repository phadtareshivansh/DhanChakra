# OPENCODE_TASKS.md
## Dhan-Chakra: Master Build Task List

This file is the single source of truth for the remaining build work. Read this whole file first, then work through the tasks in order.

---

## 0. OPERATING RULES (read before doing anything)

1. **One task at a time.** Work on the first unchecked task in the Progress Tracker. Do not start the next task until the current one is finished and I confirm.
2. **Inspect before changing.** For each task, read the relevant files first, then give me a short plan (files you will touch, new files, migrations) before editing.
3. **Branch per task.** Create a git branch named after the task id (for example `task-a1-benchmark`). Never commit to `main` directly.
4. **Test before and after.** Run the existing test suite (`docker compose exec api pytest tests -v`) and the frontend type-check (`cd frontend && npx tsc --noEmit`) before you start and after you finish. Report any difference.
5. **Never guess when unsure.** If a requirement is ambiguous, a design choice has real trade-offs, or you need information only I have (credentials, API keys, dataset locations, preferences), **stop and ask me a clear question**. I will answer and you continue. Do not invent an answer and keep going.
6. **Report real numbers only.** For any benchmark, timing or metric, report exactly what was measured. Never fabricate, round favorably, or hard-code results. If a result is unflattering, say so.
7. **No secrets or datasets in git.** Never commit credentials, `.env`, API keys, downloaded datasets or model checkpoints larger than a few MB. Document download steps instead.
8. **New migrations, never edits.** Add new migration/Cypher files for schema changes. Do not edit files that were already applied.
9. **Keep what works.** Do not refactor unrelated code. Preserve existing endpoints, role guards (Super Admin plus 2 standard users), audit logging and the privacy rules (no real PAN/Aadhaar data, hashed or synthetic identity fields only).
10. **Finish each task with a summary** containing: what changed, files touched, how to run/verify it, test results before and after, and anything left undone. Then tick the box in the Progress Tracker below and wait for me.

---

## PROGRESS TRACKER

- [x] TASK 0: Baseline audit
- [x] TASK A1: Benchmark harness
- [x] TASK A2: Public benchmark, ablation, false-positive stress test
- [x] TASK A3: Scale test
- [x] TASK B1: e-Way Bill mismatch signal
- [x] TASK B2: Temporal view and burst detection
- [x] TASK B3: Analyst feedback loop
- [x] TASK B5: LLM case summary
- [x] TASK B4: Watchlist and alerts
- [x] TASK C1: Auth hardening
- [x] TASK C3: Frontend quality
- [x] TASK C2: Ops and observability
- [x] TASK D1: Deployment
- [x] TASK D2: Docs and responsible-use

Recommended order is the order listed above (B5 before B4 is intentional).

---

## TASK 0: Baseline audit

Before any changes, report the current state:
1. Run `make env && make up && make bootstrap && make smoke` and report what passes and fails, with error output.
2. Run `docker compose exec api pytest tests -v` and report results per test file.
3. Run `cd frontend && npx tsc --noEmit` and report type errors.
4. Confirm whether a GNN checkpoint exists and loads, and whether `risk_score` is populated on Company nodes after bootstrap.
5. Confirm the auth setup: no `/auth/register` endpoint, admin-only user management endpoints work, a 4th user is rejected.

Do not fix anything in this task. Produce a clear list of what works and what does not, then stop. If anything is broken, ask me whether to fix it now or continue.

---

## TRACK A: PROVE THE ML

### TASK A1: Benchmark harness

Task: Build a reproducible model benchmark for the fraud risk scorer.

Requirements:
1. Create a benchmarks directory (for example `api/benchmarks/`) with a script `run_benchmark.py`.
2. Use one fixed, seeded, stratified train/val/test split over the synthetic graph produced by `app/services/gnn/synthetic.py`.
3. Compare four models on the SAME split:
   - Rule-only baseline (cycle membership and shared-director flags, no learning)
   - Structural features plus Logistic Regression
   - Structural features plus Gradient Boosting (sklearn is fine)
   - Our GraphSAGE (`app/services/gnn/model.py`)
4. Report F1, AUC-PR, AUC-ROC, and precision@k and recall@k for k=50 and k=100.
5. Run multiple seeds (at least 5) and report mean and standard deviation, not a single run.
6. Output `results.json`, a markdown table in `docs/benchmarks.md`, and a precision-recall curve PNG.
7. First inspect `app/services/gnn/` and tell me which labels the synthetic generator produces and whether any feature could leak the label. Ask me if you find leakage risk.

### TASK A2: Public benchmark, ablation, false-positive stress test

Task: Validate beyond our own synthetic generator and prove each signal earns its place.

Requirements:
1. Add a loader that converts an IBM AMLworld/AMLSim style transaction file into our graph schema. Document the download step in `docs/benchmarks.md`. Do not commit the dataset. Ask me where the dataset file is (or whether I want you to generate an AMLSim dataset instead) before writing the loader.
2. Run the Task A1 benchmark on that data and add a second results table.
3. Ablation: retrain GraphSAGE with each feature group removed (cycle features, shared-director features, centrality, community id, entity attributes) and report the metric drop for each.
4. False-positive stress test: generate a legitimate tight-knit supplier cluster (dense internal trade, realistic attributes, no shared directors or addresses) and report how often each model flags it.
5. State clearly in `docs/benchmarks.md` what is synthetic and what is not.

### TASK A3: Scale test

Task: Replace unverified speed claims with measured numbers.

Requirements:
1. Add a graph generator that builds synthetic graphs at 10K, 100K and 500K nodes (edges scale proportionally, planted rings included).
2. For each size, time: bulk load, WCC, Louvain, cycle detection (3 to 8 hops), centrality, GNN training, GNN inference, and p50/p95 latency of `/entities/search`, `/entities/{id}/network` and `/worklist`.
3. Use Neo4j `PROFILE` on the slowest queries, fix missing indexes or unbounded traversals, and record before/after timings.
4. Write results to `docs/performance.md`. Do not assert any number that was not measured. If the machine cannot handle 500K nodes, report the largest size that ran and say why.

---

## TRACK B: PRODUCT FEATURES

### TASK B1: e-Way Bill mismatch signal

Task: Add the e-Way Bill mismatch fraud signal.

Requirements:
1. Extend the schema so Transaction nodes carry `eway_bill_ref` (nullable) and add a simulated movement-record source (synthetic e-Way Bill records keyed by reference).
2. Flag high-value invoices with no matching movement record. Make it a feature in `app/services/gnn/features.py` and a visible evidence item in the explain endpoint.
3. Surface it in the UI: a badge on affected invoices/edges and a count on the entity page.
4. Update seed data, the hero fraud ring, tests and schema docs.
5. Use a new migration/Cypher constraint file. Ask me what value threshold should count as "high value" if it is not already configured.

### TASK B2: Temporal view and burst detection

Task: Add a time dimension to the network view.

Requirements:
1. Add an endpoint returning a ring's edges grouped by month/week with amounts and counts.
2. In `EntityNetwork.tsx` add a timeline slider that filters or animates edges by date, and a burst indicator highlighting sudden high-volume windows between the same entities.
3. Add burst detection (z-score or similar over rolling windows) to the analytics layer, expose it as a model feature and as an evidence item in explain.
4. Add tests for the burst detector with planted and non-planted cases.

### TASK B3: Analyst feedback loop

Task: Let officers label results and use those labels.

Requirements:
1. Add "Confirm fraud", "False positive" and "Needs review" actions on the entity and case pages, stored in Postgres (user, entity, label, note, timestamp) and mirrored as a property on the Neo4j node.
2. Audit-log every labeling action. Respect existing role guards.
3. Add a retraining script that prefers confirmed labels over weak labels, records the new model in `model_versions`, and keeps the previous version available for rollback.
4. Show label counts and the active model version on the dashboard.
5. Ask me whether both standard users may label, or only specific roles.

### TASK B5: LLM case summary

Task: Generate a draft case narrative from the evidence.

Requirements:
1. Add `POST /cases/{id}/summary` that builds a structured evidence object (cycle members, amounts, dates, shared directors/addresses, e-Way Bill gaps, score drivers) and asks the configured LLM for a factual one-to-two paragraph summary.
2. The prompt must forbid claims beyond the supplied evidence. The response must include the evidence object it was based on.
3. Label output clearly as "AI-drafted, requires officer review" and include it in the exported case PDF/JSON.
4. Feature-flag it, with a deterministic template fallback when no LLM key is set. Ask me which LLM provider and key variable name to use.

### TASK B4: Watchlist and alerts

Task: Add watchlist and score-change alerts.

Requirements:
1. Per-user watchlist (pin/unpin entities) in Postgres.
2. After any ingestion or rescoring job, compute score deltas for watched entities and create in-app notifications when a score crosses a risk band or a new cycle appears.
3. Add a notifications bell in `Layout.tsx` and a `/watchlist` page.
4. Scope everything by user and enforce the existing role guards.

---

## TRACK C: HARDENING

### TASK C1: Auth hardening

Task: Harden authentication now that there are exactly 3 accounts.

Requirements:
1. Rate limit `POST /auth/login` per IP and per account, with temporary lockout after repeated failures and a generic error that does not reveal whether an email exists.
2. Short-lived access tokens plus refresh tokens with server-side revocation (logout invalidates) and a token-version field so password reset invalidates all existing tokens.
3. Audit-log all admin actions, failed logins and lockouts.
4. Add security headers and a strict CORS allowlist from env.
5. Add tests for each behavior.

### TASK C3: Frontend quality

Task: Frontend polish and resilience pass.

Requirements:
1. Verify every page has loading, empty and error states matching `docs/03_UIUX_Design.md` (if that file is not in the repo, ask me for it).
2. Keyboard navigation, visible focus rings, ARIA labels on graph controls and risk badges, color-plus-label risk signaling everywhere.
3. Graph performance: cap rendered nodes with an explicit "expand" control and test with a 2,000-node neighborhood.
4. Add a small Playwright smoke suite covering the main user journey (dashboard, worklist, entity, network, explain drawer, export), and run it in CI.

### TASK C2: Ops and observability

Task: Make the stack operable.

Requirements:
1. Named volumes and a documented backup/restore script for Neo4j and Postgres.
2. Structured JSON logging with request ids, a `/metrics` endpoint (Prometheus format), and a deeper `/health` that checks both databases and the model checkpoint.
3. Add `pip-audit`, `npm audit` and Trivy image scanning to the existing GitHub Actions workflow, failing on high severity.
4. Add a Makefile target `make demo-reset` that wipes and reseeds everything, including the hero fraud ring.

---

## TRACK D: SHIP AND PRESENT

### TASK D1: Deployment

Task: Prepare a one-command production-style deployment.

Requirements:
1. Add `docker-compose.prod.yml` (no hot reload, no demo seeding unless flagged, reverse proxy with HTTPS via Caddy or nginx, secrets from env).
2. Write `docs/deploy.md` for a single VM, including firewall rules and first-boot steps for creating the Super Admin from env variables.
3. Confirm `APP_ENV=production` refuses weak secrets and `ALLOW_DEMO_SEED` stays false.
4. Ask me which hosting provider and domain I plan to use before writing provider-specific steps.

### TASK D2: Docs and responsible-use

Task: Final documentation pass.

Requirements:
1. Rewrite `README.md` to reflect the actual current state: quick start, Mermaid architecture diagram, feature list, links to `docs/benchmarks.md` and `docs/performance.md`.
2. Add `docs/limitations.md`: synthetic data, audit-prioritization not verdict, human in the loop, known false-positive modes, privacy handling.
3. Update `docs/demo_script.md` to the final feature set, with a fallback plan for each step.
4. Only describe features that actually exist and metrics that were actually measured.

---

## WHEN YOU ARE UNSURE

Stop and ask. Use this format:

```
QUESTION (Task <id>):
<the question, one sentence>
Options: <A / B / C, if applicable>
My default if you do not care: <what you would pick and why>
```

Then wait for my answer.
