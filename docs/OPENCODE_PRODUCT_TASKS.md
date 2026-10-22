# OPENCODE_PRODUCT_TASKS.md
## Dhan-Chakra: Production Product Roadmap (FinTech / RegTech)

Dhan-Chakra is now a product, not a hackathon entry. It is a graph-AI platform that helps tax authorities, banks and audit firms detect shell-company networks, circular trading and fraudulent ITC claims, with explainable evidence for every flag.

This file extends `OPENCODE_TASKS.md`. Read both. Where they conflict, this file wins.

---

## 0. OPERATING RULES

1. **One task at a time.** Work on the first unchecked task in the tracker. Do not start the next until it is finished and I confirm.
2. **Inspect, then plan, then edit.** Read the relevant code first and give me a short plan (files, migrations, risks) before changing anything.
3. **Branch per task**, named after the task id (for example `p3-1-tenancy`). Never commit to `main` directly.
4. **Test before and after.** Run backend tests, frontend type-check and lint before starting and after finishing. Report any difference.
5. **Ask, do not guess.** If a decision has product, legal, cost or architecture consequences, or needs information only I have, stop and ask using the question format at the bottom.
6. **Real measurements only.** Never fabricate or hard-code metrics, benchmark results, uptime claims or compliance claims.
7. **No secrets, datasets or large artifacts in git.**
8. **New migrations, never edits** to already-applied migrations.
9. **Backward compatibility.** Keep existing endpoints working or version them (`/api/v1`, `/api/v2`) and note the change.
10. **Privacy by default.** No raw PAN, Aadhaar or bank account numbers stored or logged. Hashed or tokenized identifiers only.
11. **Finish every task** with: what changed, files touched, how to verify, test results before and after, what is left undone. Tick the tracker and wait.

---

## WHAT CODE CANNOT SOLVE (be honest about these in all docs)

- **Real data access.** GSTN data reaches third parties through licensed GST Suvidha Providers (GSPs) or direct agreements with authorities. MCA data comes from public datasets or licensed providers. Until a customer provides data, the product runs on customer uploads and synthetic data.
- **Confirmed fraud labels.** Only customers' enforcement outcomes can supply them. The product must collect them through the feedback loop.
- **Legal documents.** Privacy policy, terms and data processing agreements need review by a lawyer. Templates only.
- **Certifications.** SOC 2 and ISO 27001 need an auditor. The product can be built audit-ready, not certified.
- **Independent penetration test.** Needs an external party.

---

## DECISIONS I NEED FROM YOU (opencode: ask these in Phase 0)

1. Primary customer: tax authority, bank/NBFC, or audit/CA firm?
2. Delivery model: multi-tenant SaaS, single-tenant on-prem/private cloud, or both?
3. Hosting region and data residency requirement (India-only?)
4. Product brand: keep "Dhan-Chakra"? Logo, brand colors, tone?
5. Languages for the UI (English only, or English and Hindi)?
6. Billing and plans needed now, or later?
7. Maximum expected data size per customer (entities, invoices per month)?

---

## PROGRESS TRACKER

**Phase 0: Foundation**
- [x] P0.1 Rebrand and baseline audit

**Phase 1: Core completion**
- [x] P1.1 Complete `OPENCODE_TASKS.md` tasks A1, A2, A3, B1, B2, B3, B5, B4, C1, C2, C3 (skip D1 and D2, superseded by Phases 7 and 8)

**Phase 2: UI/UX**
- [x] P2.1 Design system and app shell
- [x] P2.2 Core screens redesign
- [ ] P2.3 Graph investigation workspace
- [ ] P2.4 Accessibility, responsive, i18n, visual tests

**Phase 3: Identity, tenancy, security**
- [ ] P3.1 Organizations, tenancy and RBAC
- [ ] P3.2 SSO and MFA
- [ ] P3.3 API keys and rate limiting
- [ ] P3.4 Tamper-evident audit log
- [ ] P3.5 Data protection and retention

**Phase 4: Data platform**
- [ ] P4.1 Connector framework
- [ ] P4.2 Async job system
- [ ] P4.3 Data quality and schema mapping
- [ ] P4.4 Incremental graph updates and rescoring

**Phase 5: ML governance**
- [ ] P5.1 Model registry and rollback
- [ ] P5.2 Drift and quality monitoring
- [ ] P5.3 Configurable thresholds and review workflow

**Phase 6: Product surface**
- [ ] P6.1 Public API and webhooks
- [ ] P6.2 Reports and scheduled exports
- [ ] P6.3 Email notifications
- [ ] P6.4 Onboarding and in-app help
- [ ] P6.5 Admin console

**Phase 7: Reliability and operations**
- [ ] P7.1 Production deployment
- [ ] P7.2 Backup and disaster recovery
- [ ] P7.3 Observability and alerting
- [ ] P7.4 CI/CD with staging
- [ ] P7.5 Load and security testing

**Phase 8: Launch**
- [ ] P8.1 Legal and security documentation
- [ ] P8.2 Product site and public docs
- [ ] P8.3 Release checklist

---

## PHASE 0: FOUNDATION

### P0.1 Rebrand and baseline audit

Task: Remove hackathon framing and establish a verified baseline.

Requirements:
1. Search the repo, docs and UI for hackathon, SIH and competition wording and replace with product language. Keep research references.
2. Rewrite `README.md` as a product README: purpose, architecture, quick start, status of each module.
3. Run the full stack, tests, type-check and smoke checks. Report what works and what does not. Do not fix yet.
4. Ask me the seven decisions above.

---

## PHASE 2: UI/UX (clean, calm, trustworthy)

Design direction: a forensic analyst tool. Dark and light themes, high information density without clutter, risk colors used only for risk, explainability always one click away. Follow `docs/03_UIUX_Design.md` as the starting point and improve it.

### P2.1 Design system and app shell

Requirements:
1. Create design tokens (color, type, spacing, radius, elevation, motion) as CSS variables and Tailwind config. Support dark and light themes with a toggle that respects system preference.
2. Build a documented component library: Button, Input, Select, Table (sortable, sticky header, column visibility), Tabs, Modal, Drawer, Toast, Tooltip, Badge, RiskBadge, StatTile, EmptyState, Skeleton, Pagination, FilterChips, Breadcrumbs.
3. Build the app shell: left sidebar navigation (collapsible), top bar with global search and command palette (Cmd/Ctrl+K), notifications bell, user menu, organization switcher placeholder.
4. Add Storybook (or equivalent) with every component and its states.
5. Ask me for brand colors and logo if not decided.

### P2.2 Core screens redesign

Requirements:
1. Dashboard: key stat tiles, risk distribution chart, ITC-at-risk trend, top rings, recent activity.
2. Worklist: dense table with saved views, multi-filter, bulk actions (assign, label, add to case), keyboard navigation.
3. Entity page: summary header, risk score with driver breakdown, tabs for network, transactions, directors/addresses, evidence, history, notes.
4. Cases: board and list views, assignment, status, comments, activity timeline.
5. Every screen has designed loading (skeleton), empty and error states with helpful copy.
6. Consistent microcopy: plain language, no jargon without a tooltip.

### P2.3 Graph investigation workspace

Requirements:
1. Full-bleed canvas with a left filter panel and right inspector drawer.
2. Node and edge styling per design doc: entity type by shape or color, risk by ring and label, cycle edges highlighted with direction.
3. Controls: expand neighbors, collapse, pin, hide, focus on ring, fit to view, reset, layout toggle (force, hierarchical), search within graph.
4. Time slider (from B2), minimap, legend, export as PNG and SVG.
5. Performance guard: render cap with explicit expand, canvas or WebGL fallback beyond a node threshold. Test with 2,000 and 10,000 node neighborhoods and report frame rates.
6. Path finder: pick two entities, show shortest connecting paths.

### P2.4 Accessibility, responsive, i18n, visual tests

Requirements:
1. WCAG 2.2 AA: contrast, focus order, visible focus, keyboard-only operation, screen-reader labels, reduced-motion support. Provide a text/table alternative for the graph.
2. Responsive layouts for tablet widths; phone shows read-only essentials with a clear notice for the graph.
3. i18n framework with English complete and Hindi if I chose it. No hard-coded user-facing strings.
4. Visual regression tests (Playwright screenshots) for key screens in both themes, run in CI.
5. Run automated accessibility checks (axe) in CI.

---

## PHASE 3: IDENTITY, TENANCY, SECURITY

### P3.1 Organizations, tenancy and RBAC

Note: the current setup caps users at one Super Admin and two standard users. A product needs organizations and many users. Ask me before changing this.

Requirements:
1. Add `organizations` and `memberships`. Every business table and every graph node/edge carries an `org_id`. Choose and justify the graph isolation approach (property-based filter on every query, or separate Neo4j databases per org) and ask me which I prefer.
2. Roles: Platform Admin, Org Admin, Investigator, Reviewer, Read-only. Define a permission matrix in code and docs. Enforce with a single reusable authorization layer, not per-route checks.
3. Invitation-based onboarding only (no open sign-up). Org Admins invite members by email with expiring tokens.
4. Add cross-tenant isolation tests: user from org A can never read, write or infer org B data via any endpoint, including search, export and explain.

### P3.2 SSO and MFA

Requirements:
1. OIDC single sign-on (Google Workspace and Microsoft Entra at minimum), configurable per organization.
2. TOTP multi-factor authentication with recovery codes, enforceable per organization.
3. Session management: device list, revoke sessions, idle timeout, absolute timeout.

### P3.3 API keys and rate limiting

Requirements:
1. Scoped API keys per organization (read, write, admin scopes), hashed at rest, shown once, revocable, with last-used tracking.
2. Rate limits per key, per user and per IP, with `429` and `Retry-After`. Configurable per plan.
3. Document the limits.

### P3.4 Tamper-evident audit log

Requirements:
1. Append-only audit log where each entry includes the hash of the previous entry (hash chain), scoped per organization.
2. Record: logins, failed logins, permission changes, data views of cases, exports, label changes, model changes, admin actions, API key events.
3. Integrity verification endpoint and UI button that recomputes the chain and reports pass or fail with the first broken entry.
4. Periodic signed checkpoints (store the head hash externally, for example object storage).
5. Exported case bundles include a manifest hash so alteration after export is detectable.
6. State plainly in docs that this is tamper-evident, not tamper-proof.

### P3.5 Data protection and retention

Requirements:
1. Align with India's Digital Personal Data Protection Act principles: purpose limitation, minimal collection, retention limits, deletion and correction workflows, breach response runbook. Ask me which legal basis and roles (fiduciary or processor) apply per customer type.
2. Encrypt at rest (database volumes, backups, object storage) and in transit (TLS everywhere, including internal services where feasible).
3. Field-level encryption or tokenization for sensitive identifiers.
4. Configurable retention policies per organization with scheduled purge jobs and purge audit entries.
5. Organization data export and full deletion endpoints.
6. Log scrubbing: verify no sensitive values appear in logs.
7. Secrets via environment or a secrets manager; document rotation.

---

## PHASE 4: DATA PLATFORM

### P4.1 Connector framework

Requirements:
1. Define a connector interface (`fetch`, `validate`, `map`, `checkpoint`) and implement: CSV/Excel upload, SFTP drop folder, and a generic REST pull connector.
2. Add a GSP/GSTN adapter skeleton with clear configuration, mocked responses and tests, ready for real credentials. Do not claim live GSTN access.
3. Add MCA company master data importer using the open government dataset format.
4. Credentials per connector are encrypted and scoped to the organization.

### P4.2 Async job system

Requirements:
1. Move ingestion, analytics, scoring, training and exports to a job queue (for example Arq, Celery or RQ with Redis). Ask me which I prefer.
2. Job model with status, progress, logs, retries with backoff, cancellation, idempotency keys.
3. UI: jobs page with live progress and error details.
4. Ensure API requests never block on heavy work.

### P4.3 Data quality and schema mapping

Requirements:
1. Validation rules (GSTIN format and checksum, CIN format, date sanity, negative amounts, duplicates) with a per-file report showing accepted, rejected and why.
2. Column-mapping UI for uploaded files with saved mapping templates.
3. Partial success: valid rows are loaded, invalid rows are downloadable as an error file.
4. Data freshness indicators per source on the dashboard.

### P4.4 Incremental graph updates and rescoring

Requirements:
1. Upsert semantics so re-ingesting the same data is idempotent.
2. Incremental recomputation: only affected components are re-analyzed and rescored after new data, with full recompute as a scheduled fallback.
3. Record score history per entity so the UI can show trends and change reasons.
4. Benchmark incremental vs full recompute and record results in `docs/performance.md`.

---

## PHASE 5: ML GOVERNANCE

### P5.1 Model registry and rollback

Requirements:
1. Registry with versions, training data description and hash, parameters, metrics, author, created time, status (candidate, champion, retired).
2. Champion/challenger: score with both on the same data and compare before promotion.
3. One-click rollback with audit entry. Scores record the model version that produced them.
4. Training is reproducible: fixed seeds, pinned dependencies, stored config.

### P5.2 Drift and quality monitoring

Requirements:
1. Monitor feature distributions and score distributions against the training baseline (for example PSI), per organization.
2. Track label-based quality once feedback exists: precision at k, false-positive rate by segment.
3. Alert when drift or quality crosses configured thresholds, and show a model health page.

### P5.3 Configurable thresholds and review workflow

Requirements:
1. Org-level risk band thresholds and cycle length limits, with change history and audit.
2. Review workflow: flag, assign, review, decide (confirm, false positive, needs info), with required notes and optional second reviewer for escalations.
3. Case SLA timers and overdue indicators.
4. Show a reviewer fairness view: false-positive rate by sector and state, to catch systematic bias.

---

## PHASE 6: PRODUCT SURFACE

### P6.1 Public API and webhooks

Requirements:
1. Versioned REST API with OpenAPI spec, consistent error envelope, pagination, filtering, idempotency keys on writes.
2. Webhooks for events (new high-risk ring, score band change, case status change) with HMAC signatures, retries and a delivery log.
3. Generated API docs page and a sample client in Python.
4. Contract tests for every public endpoint.

### P6.2 Reports and scheduled exports

Requirements:
1. Case report (PDF and JSON) with evidence subgraph image, score drivers, timeline, reviewer decisions, audit manifest hash.
2. Portfolio report: rings by state and sector, ITC at risk, trend.
3. Scheduled reports delivered by email or to storage.
4. Reports state data freshness and model version.

### P6.3 Email notifications

Requirements:
1. Transactional email through a provider abstraction (SMTP and one API provider). Ask me which provider.
2. Templates for invitations, password reset, alerts, digests, SLA reminders.
3. Per-user notification preferences.

### P6.4 Onboarding and in-app help

Requirements:
1. First-run checklist: connect data, run first analysis, review first ring, invite a teammate.
2. Contextual help tooltips, a glossary (ITC, GSTIN, DIN, CIN, circular trading), and an in-app guide to reading the graph and risk scores.
3. Sample data mode so new users can explore before connecting real data.

### P6.5 Admin console

Requirements:
1. Org settings, members and roles, SSO config, API keys, retention, thresholds, connectors.
2. Usage view (entities, jobs, API calls) and plan limits if billing is required later.
3. Platform admin view across organizations, restricted and fully audited.

---

## PHASE 7: RELIABILITY AND OPERATIONS

### P7.1 Production deployment

Requirements:
1. Production images (multi-stage, non-root, pinned, minimal), no hot reload, no demo seeding.
2. Deployment as Docker Compose behind a reverse proxy with HTTPS and automatic certificates, plus Kubernetes manifests or Helm chart if I choose to scale out. Ask me which target.
3. Infrastructure as code (Terraform or equivalent) for one cloud provider. Ask me which.
4. Startup checks refuse to boot with weak or missing secrets.
5. Zero-downtime migration procedure documented and tested.

### P7.2 Backup and disaster recovery

Requirements:
1. Automated encrypted backups of Neo4j, Postgres and object storage to a separate location.
2. Documented RPO and RTO targets (ask me), and a restore drill script. Run the drill and record the real time taken.
3. Runbook for common failures.

### P7.3 Observability and alerting

Requirements:
1. Structured logs with request ids and organization ids, metrics (Prometheus), tracing (OpenTelemetry).
2. Dashboards (Grafana or equivalent) for API latency and errors, job queue depth, database health, model health.
3. Alert rules with severity and runbook links. Public status page.

### P7.4 CI/CD with staging

Requirements:
1. Pipeline: lint, type-check, unit and integration tests, Playwright E2E, accessibility, dependency and image scans, build, push.
2. Staging environment deployed automatically from `main`, production deployed by tagged release with manual approval.
3. Database migration checks in CI against a copy of the previous schema.
4. Semantic versioning and a generated changelog.

### P7.5 Load and security testing

Requirements:
1. Load tests (k6 or Locust) for key endpoints and the job system at the data sizes I specified. Publish real results with the hardware used.
2. OWASP ZAP baseline scan and an OWASP Top 10 checklist review mapped to the codebase. Fix findings.
3. Dependency, secret and container scanning in CI.
4. Prepare a scoped brief for an external penetration test.

---

## PHASE 8: LAUNCH

### P8.1 Legal and security documentation

Requirements (templates for lawyer review, clearly marked as drafts):
1. Privacy policy, terms of service, data processing agreement, acceptable use policy.
2. Security overview: architecture, encryption, access control, audit, backup, incident response.
3. Responsible-use statement: the system prioritizes cases for human review, never decides guilt; explain false-positive risks and mitigation.
4. Model card: purpose, data, metrics, limits, monitoring.

### P8.2 Product site and public docs

Requirements:
1. Landing page: problem, how it works, explainability, security, contact. Clean and consistent with the design system.
2. Documentation site: user guide, admin guide, API reference, FAQ.
3. Demo environment with sample data and a guided tour.

### P8.3 Release checklist

Requirements:
1. Final checklist covering tests, security scan results, backup drill, load test results, docs, legal drafts, monitoring and alerts live, rollback plan.
2. Known limitations list, honestly maintained.
3. Support process: contact, severity levels, response targets (ask me for targets).

---

## WHEN YOU ARE UNSURE

Stop and ask:

```
QUESTION (Task <id>):
<one sentence>
Options: <A / B / C>
My default if you do not care: <choice and reason>
```

Then wait for my answer.
