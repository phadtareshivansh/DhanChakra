# Findings and fixes (hand-written)

The tables above are generated. This section is written by hand and records the
**specific problems the scale test uncovered** and what was changed. All numbers
were measured on the same machine as the tables.

## Finding 1 — the database shipped with no indexes at all

`graph/cypher/constraints.cypher` defines the schema's uniqueness constraints,
but nothing in the stack ever **applied** it. `SHOW INDEXES` on a freshly
booted database returned only the two default token-lookup indexes and
`SHOW CONSTRAINTS` returned none. Every property `MATCH`/`MERGE` was therefore
a full label scan, and the row-at-a-time loader was O(N²).

**Fix.** Added `graph/cypher/indexes.cypher` (all statements `IF NOT EXISTS`),
a small idempotent applier `api/benchmarks/apply_schema.py`, a `make
apply-schema` target, and wired the applier into the scale test so the schema is
in place before loading. `docker-compose.yml` mounts `./graph/cypher:/cypher:ro`
into the api container so the applier can read the files.

**Before/after (measured, 10,000 companies, batched `UNWIND` loader):**

| Stage | Before indexes | After indexes |
|---|---|---|
| bulk load (2,000 companies) | 9.75 s | 0.37 s |
| bulk load (10,000 companies) | **281.9 s** | **2.4 s** |

That is roughly a **117×** speed-up at 10K, on the same hardware and seed. The
gap widens with size because the un-indexed cost is quadratic.

## Finding 2 — betweenness centrality is O(V·E) and unusable at scale

`GET /entities/{id}/centrality` calls `graph_service.compute_centrality`, which
streams **betweenness** from GDS. Betweenness uses Brandes' algorithm, which is
O(V·E). At 10K nodes it returns in ~2.5 s; at 100K nodes it did not return
within the 300 s timeout and had to be terminated server-side.

This is not on the main analytics path — `run_structural_analytics` only writes
**PageRank**, never betweenness — but the dedicated endpoint exposes it, so at
large graph sizes that endpoint is effectively unusable.

**Recommendation (not yet implemented — a product decision).** Either approximate
betweenness (`gds.betweenness` sampling parameters), compute it only for a
bounded subgraph around the entity of interest, or drop it from the endpoint and
rely on PageRank/degree. The scale test records centrality as an **optional**
stage so a slow betweenness does not hide the rest of the pipeline's numbers.

## Finding 3 — the GNN pipeline does not scale to 100K in memory

The GNN training step fine-tunes on the **live** graph, building a dense
adjacency. At 10K companies it fits; at 100K the process is killed by the OOM
killer (SIGKILL, which Python cannot catch). This is why each graph size runs
in its **own child process**: the failure is contained and reported rather than
aborting the whole run.

**Recommendation (not yet implemented).** Build the adjacency in
sparse/edge-list form, or batch neighbour sampling during fine-tuning, so memory
scales with edges rather than V².

## Finding 4 — Neo4j's default heap is the first ceiling, not the app

At the default `NEO4J_HEAP_MAX=1G`, a 100K-company load **fails inside Neo4j**
with `Neo4j.TransientError.General.OutOfMemoryError`. Raising the heap to 3G
(and pagecache to 1G) let the same 100K load complete in ~16 s.

**Implication for operators.** `docs/performance.md` numbers are only
reproducible at the heap setting recorded in the Environment table. The default
compose values target the demo dataset, not 100K+ graphs; the section above
states the heap used.

## What was NOT measured

- No real customer data. The graphs are the seeded `scale_gen` generator.
- No multi-node cluster, no read replicas, no network latency — single host,
  single Neo4j.
- Endpoint figures are **Neo4j query times** for the same Cypher the routes
  issue, not full HTTP round-trips through FastAPI.
