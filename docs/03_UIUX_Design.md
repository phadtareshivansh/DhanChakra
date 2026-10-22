# UI/UX Design System
## Dhan-Chakra — Graph-AI Engine for Shell Company Loops & GST Fraud Detection

**Version:** 1.0 | **Companion to:** 04_AppFlow.md

---

## 1. Design Philosophy

Dhan-Chakra is a forensic instrument, not a consumer app. The design language borrows from **control-room / intelligence-dashboard** aesthetics: dark, focused, high-contrast, data-dense but never cluttered. Every visual choice should reinforce two things — **trust** (this tool's findings are defensible) and **clarity** (an auditor under time pressure can find the loop in seconds). Playful or "startup pastel" styling is deliberately avoided; the tone is closer to a SOC (Security Operations Center) console or a financial trading terminal than a marketing site.

**Design principles:**
1. **Evidence over decoration.** The graph visualization is the hero element on every screen that shows one; chrome around it stays quiet.
2. **Color means risk, not brand.** Red/amber/green is reserved exclusively for risk-severity signaling — never used decoratively elsewhere, so its meaning stays unambiguous.
3. **Explainability is always one click away.** No score appears without a visible affordance to see why.
4. **Dense but breathable.** Tables and worklists are information-dense (auditors want to scan many rows fast) but use spacing/typography to avoid visual fatigue.

## 2. Color Palette

### 2.1 Base (Dark Mode — Primary Theme)

| Token | Hex | Usage |
|---|---|---|
| `bg-canvas` | `#0B0F14` | App background, graph canvas backdrop |
| `bg-surface` | `#121821` | Card/panel background |
| `bg-surface-raised` | `#1A2230` | Modals, dropdowns, elevated panels |
| `border-subtle` | `#26303E` | Card borders, table dividers |
| `text-primary` | `#E7EDF3` | Primary text |
| `text-secondary` | `#8B99AB` | Secondary/meta text, labels |
| `text-disabled` | `#4C5768` | Disabled states |

### 2.2 Brand / Accent

| Token | Hex | Usage |
|---|---|---|
| `accent-primary` (Chakra Teal) | `#1F8A8C` | Primary buttons, active nav, links, graph edges (normal) |
| `accent-primary-hover` | `#26A3A6` | Hover state |
| `accent-secondary` (Dhan Amber) | `#D6A94A` | Secondary CTAs, highlighted metrics, brand mark |
| `accent-focus-ring` | `#4FD1D4` | Focus outlines, keyboard nav |

### 2.3 Risk Semantic Colors (reserved exclusively for risk signaling)

| Token | Hex | Meaning |
|---|---|---|
| `risk-critical` | `#E5484D` | Score ≥ 85 — confirmed-pattern-strength fraud ring |
| `risk-high` | `#F2994A` | Score 65–84 |
| `risk-medium` | `#F2C94C` | Score 40–64 |
| `risk-low` | `#6FCF97` | Score < 40 — likely legitimate |
| `risk-neutral` | `#8B99AB` | Unscored / insufficient data |

### 2.4 Light Mode (Secondary Theme — for print/export/report views)

| Token | Hex |
|---|---|
| `bg-canvas-light` | `#F7F9FB` |
| `bg-surface-light` | `#FFFFFF` |
| `border-subtle-light` | `#E1E7ED` |
| `text-primary-light` | `#141B24` |
| `text-secondary-light` | `#5B6B7D` |

*Note: exported case PDFs (§10 of TRD) always use light mode for print-friendliness; the live dashboard defaults to dark mode.*

## 3. Typography

| Role | Font | Weight | Size (desktop) | Notes |
|---|---|---|---|---|
| Display / page titles | **Inter** (or **IBM Plex Sans** as fallback) | 700 | 28–32px | Used sparingly — page-level headers only |
| Section headings | Inter | 600 | 20–22px | |
| Body text | Inter | 400 | 14–15px | Line-height 1.5 |
| Table/data-dense text | **IBM Plex Sans** or **Inter** | 400–500 | 13px | Slightly tighter line-height (1.3) for scan-density |
| Numeric / risk scores / IDs (GSTIN, CIN, DIN) | **IBM Plex Mono** | 500 | 13–15px | Monospace for alignment and to visually distinguish identifiers from prose |
| Micro-labels / badges | Inter | 600, uppercase, letter-spacing 0.04em | 11px | |

**Rationale:** Inter is chosen for its excellent legibility at small sizes and neutral, professional character; IBM Plex Mono for identifiers (GSTIN/CIN/DIN, hashes, amounts) gives the interface a "systems/terminal" credibility cue and makes numeric scanning easier — auditors comparing IDs benefit from fixed-width alignment.

## 4. Spacing & Layout Grid

- **Base unit:** 4px. All spacing/margins/padding are multiples of 4 (4, 8, 12, 16, 24, 32, 48, 64).
- **Grid:** 12-column responsive grid, max content width 1440px, 24px gutters on desktop, 16px on tablet.
- **Card padding:** 16px (compact) / 24px (standard) / 32px (feature panels).
- **Graph canvas:** always full-bleed within its panel — never boxed in with heavy padding, since screen real estate for the network view is the top priority.

## 5. Core Components

### 5.1 Risk Badge
Pill-shaped, colored per §2.3 semantic tokens, always paired with the numeric score (e.g., "● 87 Critical"). Never color alone — always score + label + color, for colorblind-safe redundancy.

### 5.2 Entity Card
Compact card showing: entity name, GSTIN/CIN (monospace), risk badge, community/cluster tag, and a "View Network →" action. Used in worklist rows and search results.

### 5.3 Network Graph Canvas (D3 force-directed)
- Nodes sized by degree/centrality, colored by entity type (Company = teal, Director = amber, Address = grey, BankAccount = slate) with risk-flagged nodes getting a colored ring overlay (§2.3) rather than changing the base fill — so entity-type and risk-level are both visible simultaneously.
- Edges: default `border-subtle`-tone; edges that are part of a detected cycle render in `risk-critical` red and slightly thicker, with directional arrowheads.
- Hover: tooltip with entity name/ID/score. Click: opens the Entity Detail panel (right-side drawer) without leaving the canvas.
- Zoom/pan enabled; a "Fit to view" and "Reset" control pinned to bottom-right of canvas.

### 5.4 Explainability Panel
Slide-in right-hand drawer triggered from any risk badge. Shows: (1) the score, (2) a mini-subgraph rendering of just the evidence (the loop / shared director / burst), (3) a 2–3 line plain-language reason ("Flagged because it forms a 4-hop invoice cycle with 3 other entities, totaling ₹2.3Cr, over 11 days"), (4) a "View full network" link back to the main canvas.

### 5.5 Worklist Table
Dense data table: sortable columns (Risk Score, Entity Name, State, Sector, Last Filing Date, Community Size), sticky header, row-level risk badge, pagination footer. Filter bar above the table (state, sector, score range, date range) using pill/chip filters rather than heavy dropdown forms.

### 5.6 Stat Tiles (Dashboard Overview)
Four to six tiles at the top of the dashboard: Entities Scanned, Flagged Rings, Estimated ITC at Risk (₹), Top Risk State. Large numeral (Plex Mono, 32px), small label above in micro-label style.

### 5.7 Buttons
- **Primary:** filled `accent-primary`, white text, 8px radius.
- **Secondary:** outline `border-subtle`, `text-primary` text.
- **Destructive/critical action** (e.g., "Confirm fraud escalation"): filled `risk-critical`.
- All buttons: 40px height (standard), 32px (compact/inline table actions).

### 5.8 Empty / Loading States
Loading: skeleton shimmer in `bg-surface-raised` tone, never a generic spinner alone on data-heavy views. Empty state: short reassuring copy + icon, e.g., "No entities match these filters — try widening the risk range."

## 6. Iconography

Use a single consistent icon set (**Lucide** — matches the available `lucide-react` library) at 1.5px stroke weight, sized 16/20/24px depending on context. Icons are functional (search, filter, export, expand-network, alert-triangle for risk) — never purely decorative.

## 7. Interaction & Motion

- Transitions: 150–200ms ease-out for hovers/panel slides; graph layout force-simulation settles over ~1–2s on load, then freezes (no perpetual jitter, which fatigues users staring at it for minutes).
- Focus states: always visible `accent-focus-ring` outline — this is an internal tool used by officers who may rely on keyboard navigation for speed.
- No unnecessary animation on data-dense screens (worklist, tables) — motion is reserved for the graph canvas and panel transitions.

## 8. Accessibility

- Minimum contrast ratio 4.5:1 for body text against its background in both themes (verified against the palette above).
- Risk signaling always redundant (color + label + icon), never color-only.
- All interactive elements keyboard-reachable and screen-reader labeled (critical for a govt/enterprise tool likely subject to accessibility audit in production).

## 9. Sample Screen Inventory

1. **Dashboard / Overview** — stat tiles + top-risk-entities preview + quick search.
2. **Worklist** — full filterable/sortable table of ranked entities.
3. **Entity Detail + Network Explorer** — split view: entity metadata panel (left) + full-bleed D3 graph canvas (right), explainability drawer slides over the canvas on demand.
4. **Case Export Preview** — light-mode, print-ready summary of a selected case before export.
5. **Ingestion / Admin (demo-only)** — simple upload form for CSV/PDF ingestion, with a progress/status list.

*(See 04_AppFlow.md for the navigation structure and screen-to-screen flow connecting these.)*
