# Graph Analytics Layer

This layer contains Cypher queries and GDS procedures for structural analytics.

## Files

- `constraints.cypher` — Neo4j uniqueness constraints (per 05_Backend_Schema.md §2.4)
- `seed.cypher` — Seed data for demo (per 05_Backend_Schema.md §4)
- `analytics/` — GDS procedures and Cypher queries

## Applying Constraints

```bash
# Credentials come from .env (NEO4J_USER / NEO4J_PASSWORD), never hardcoded
cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -f constraints.cypher
```

## Loading Seed Data

```bash
cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -f seed.cypher
```