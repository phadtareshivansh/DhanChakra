# Dhan-Chakra — Architecture Slide

One slide for a product/architecture overview (reuse of TRD §1 pipeline, annotated with what each layer produced in this
build). Renders as Mermaid in GitHub/VS Code/Marp; an SVG export of the same diagram can be produced
for the deck.

## Pipeline (Mermaid)

```mermaid
flowchart LR
    subgraph ING["1 · Ingestion"]
        A1["CSV (MCA / GST)"] --> A2["Agentic PDF agent<br/>{director, DIN, address,<br/>shareholding} + confidence"]
        A2 --> A3["Manual confirm<br/>(low-confidence)"]
    end

    subgraph GRAPH["2 · Graph Construction"]
        B["Neo4j Property Graph<br/>Company · Director · Address ·<br/>BankAccount · Transaction · GSTINFiling"]
    end

    subgraph SA["3 · Structural Analytics (GDS)"]
        C1["WCC / Louvain communities"]
        C2["Invoice loop detection<br/>₹500K ring: Orbit → Harbor → Summit"]
        C3["Entity resolution<br/>RESOLVED_AS (fuzzy + deterministic)"]
    end

    subgraph ML["4 · Learned Risk Scoring"]
        D["GraphSAGE (PyTorch)<br/>8 structural features<br/>weak labels + synthetic pretraining"]
    end

    subgraph EXP["5 · Explainability"]
        E["Evidence subgraph +<br/>plain-language reason"]
    end

    subgraph API["6 · API Layer"]
        F["FastAPI /api/v1<br/>worklist · network · explain ·<br/>cases · ingest"]
    end

    subgraph UI["7 · Web UI"]
        G["React + D3 force graph<br/>worklist · dashboard · case export"]
    end

    ING --> GRAPH --> SA --> ML --> EXP --> API --> UI
    SA --> API
    ML --> API
```

## Annotated build facts (for the talk track)

| Layer | What is real in this build |
|---|---|
| Ingestion | CSV loader (MCA/GST), agentic PDF extraction with per-field confidence, review-before-commit |
| Graph | Neo4j 5 + GDS, schema per `05_Backend_Schema.md` §2 |
| Structural | GDS WCC/Louvain, Cypher variable-length cycles → 1 ring ₹500K; entity resolution (Jaro–Winkler + exact DIN/address/bank) |
| Risk scoring | GraphSAGE, checkpoint `gnn_risk_v1`, benchmark F1 0.51 / AUC-PR 1.0 / recall@k 1.0; live F1 0.67 |
| Explainability | Evidence subgraph + natural-language flag reason per entity |
| API/UI | 15 frontend modules, 40 API tests green, case export bundles evidence + subgraph |

## Diagram variants
- **Dark slide:** swap flowchart node fills for the app's design tokens (`--accent`/`--surface`).
- **Print (light):** `Demo_Script.md` Journey C shows the print-ready export already.