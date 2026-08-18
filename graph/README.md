# Graph Analytics Layer

This layer contains Cypher queries and GDS procedures for structural analytics.

## Files

- `constraints.cypher` — Neo4j uniqueness constraints (per 05_Backend_Schema.md §2.4)
- `seed.cypher` — Seed data for demo (per 05_Backend_Schema.md §4)
- `analytics/` — GDS procedures and Cypher queries

## Applying Constraints

```bash
cypher-shell -u neo4j -p dhanchakra123 -f constraints.cypher
```

## Loading Seed Data

```bash
cypher-shell -u neo4j -p dhanchakra123 -f seed.cypher
```