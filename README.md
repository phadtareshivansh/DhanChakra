# Dhan-Chakra — Phase 0 Complete

## Services Running

- **Neo4j** (bolt://localhost:7687, http://localhost:7474)
- **PostgreSQL** (postgresql://localhost:5432/dhanchakra)
- **FastAPI** (http://localhost:8000, docs at /docs)
- **React Frontend** (http://localhost:5173)

## Quick Start

```bash
cd /Users/shivanshphadtare/Documents/SIH2026
cp .env.example .env
# Edit .env if needed
docker compose up -d
```

## Verification

```bash
# Check all services healthy
docker compose ps

# Apply Neo4j constraints
cat graph/cypher/constraints.cypher | docker exec -i dhanchakra-neo4j cypher-shell -u neo4j -p dhanchakra123

# Load seed data
cat graph/cypher/seed.cypher | docker exec -i dhanchakra-neo4j cypher-shell -u neo4j -p dhanchakra123

# Check API health
curl http://localhost:8000/health

# Check frontend
open http://localhost:5173
```

## Project Structure

```
project-root/
├── docker-compose.yml
├── .env.example
├── .env
├── ingestion/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── scripts/
│   │   ├── mca_loader.py
│   │   └── gst_loader.py
│   └── README.md
├── graph/
│   ├── cypher/
│   │   ├── constraints.cypher
│   │   ├── seed.cypher
│   │   └── analytics/
│   └── README.md
├── analytics/
│   ├── notebooks/
│   └── README.md
├── api/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── deps.py
│   │   ├── models/
│   │   │   └── schemas.py
│   │   ├── routes/
│   │   │   └── entities.py
│   │   └── deps.py
│   ├── migrations/
│   │   ├── 001_enable_extensions.sql
│   │   ├── 002_users.sql
│   │   ├── 003_cases.sql
│   │   ├── 004_audit_log.sql
│   │   ├── 005_ingestion_jobs.sql
│   │   └── 006_companies.sql
│   └── README.md
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── index.css
│   │   ├── components/
│   │   │   └── Layout.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── EntitySearch.tsx
│   │   │   ├── EntityNetwork.tsx
│   │   │   ├── LoopsView.tsx
│   │   │   └── CasesView.tsx
│   │   ├── utils/
│   │   │   └── api.ts
│   │   └── types/
│   │       └── api.ts
│   └── public/
│       └── favicon.svg
├── shared/
│   └── types/
│       └── index.ts
└── files/
    ├── 01_PRD.md
    ├── 02_TRD.md
    ├── 03_UIUX_Design.md
    ├── 04_AppFlow.md
    ├── 05_Backend_Schema.md
    └── 06_Implementation_Plan.md
```

## Next Steps (Phase 1)

1. Structural MVP: NetworkX prototype → Neo4j Cypher/GDS
2. FastAPI endpoints for search, entity detail, network
3. Minimal frontend with search and network view