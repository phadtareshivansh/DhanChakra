"""A3 scale-test graph generator and fast batched Neo4j loader.

Standalone by design: it does **not** touch `app/services/gnn/synthetic.py`
(that generator is pinned and used by the model benchmark). This module emits a
realistic property-graph shape at scale — Companies joined into planted invoice
rings, plus directors, addresses, bank accounts and per-invoice Transactions —
and loads it into Neo4j with batched `UNWIND` writes.

Two things matter for an honest scale test:

1. **The load path is batched.** `ingestion/scripts/load_sample.py` issues one
   Cypher round-trip per row, which is fine for 8 rows and unusable at 500K. To
   make "bulk load" a meaningful stage we load with `UNWIND $rows` in chunks.
   The row-at-a-time path is measured separately for contrast (see
   `run_scale_test.py --compare-naive-load`).
2. **Size ceilings are real.** At 100K+ companies a dense feature matrix / GNN
   adjacency does not fit in memory; the generator itself is cheap, but the
   downstream stages are not. The runner reports the largest size that actually
   completed and says why, rather than pretending.

Usage (inside the api container, where Neo4j is reachable):

    python /benchmarks/scale_gen.py --nodes 10000 --seed 1 --load
    python /benchmarks/scale_gen.py --nodes 100000 --seed 1 --load --batch 5000

Importable API:

    from scale_gen import build_rows, load_rows, wipe_scale_data
"""

from __future__ import annotations

import argparse
import hashlib
import os
import random
import sys
import time
from typing import Any, Dict, List, Tuple

# --- Neo4j connection (env, same contract as the rest of the repo) ----------

def _load_dotenv(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


for candidate in ("/app/.env", os.path.join(os.path.dirname(__file__), "..", "..", ".env")):
    _load_dotenv(candidate)

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

# Marker property so scale-test data is always identifiable and removable.
SCALE_TAG = "scale_a3"


# --- Generator ---------------------------------------------------------------

def build_rows(
    n_nodes: int,
    seed: int = 1,
    ring_count: int | None = None,
    ring_min: int = 4,
    ring_max: int = 8,
    edges_per_node: float = 2.0,
    n_directors: int | None = None,
    n_addresses: int | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Build in-memory row sets for a graph of roughly ``n_nodes`` companies.

    "nodes" counts **Company** nodes; directors/addresses/transactions are sized
    proportionally so the total graph is a realistic multiple of that. Planted
    rings are the same closed-loop shape the product detects (3–8 hops).

    Returns a dict of row lists: ``companies``, ``directors``, ``addresses``,
    ``banks``, ``edges`` (company→company invoice chains stored as Transaction
    nodes in ``transactions``).
    """
    rng = random.Random(seed)
    n = int(n_nodes)

    # ~1 ring per 2,000 companies, at least a few, so rings are ~0.3% of nodes
    # (a realistic needle-in-haystack prevalence, not a toy ratio).
    if ring_count is None:
        ring_count = max(2, n // 2000)
    if n_directors is None:
        n_directors = max(1, int(n * 0.6))
    if n_addresses is None:
        n_addresses = max(1, int(n * 0.5))

    companies: List[Dict[str, Any]] = []
    for i in range(n):
        cin = f"L{rng.randrange(10000, 99999)}MH2020PLC{rng.randrange(100000, 999999)}"
        companies.append({
            "cin": cin,
            "gstin": f"27ABCDE{i:06d}Z{rng.randrange(1, 9)}",
            "name": f"ScaleCo {i:07d} Pvt Ltd",
            "nic_code": f"{rng.randrange(1000, 9999)}",
            "paid_up_capital": float(rng.randrange(1_000_000, 90_000_000)),
            "status": "Active",
            "ring_id": -1,
        })

    # Plant closed invoice loops: members[i] -> members[i+1] -> ... -> members[0]
    edges: List[Tuple[int, int]] = []
    ring_members: Dict[int, int] = {}
    next_idx = 0
    for r in range(ring_count):
        size = rng.randint(ring_min, ring_max)
        members = list(range(next_idx, min(next_idx + size, n)))
        next_idx += size
        if len(members) < 3:
            break
        for k in range(len(members)):
            a, b = members[k], members[(k + 1) % len(members)]
            edges.append((a, b))
            ring_members[a] = r
            companies[a]["ring_id"] = r

    # Background traffic: each non-ring company bills a few others.
    for i in range(n):
        if companies[i]["ring_id"] >= 0:
            continue
        for _ in range(rng.randint(1, max(1, int(edges_per_node * 2)))):
            j = rng.randrange(n)
            if j != i:
                edges.append((i, j))

    # Directors / addresses / banks: mostly shared by ring members (the shell
    # pattern the product looks for), otherwise spread around.
    seen_dirs: set[str] = set()
    directors: List[Dict[str, Any]] = []
    for i in range(n):
        count = 2 if companies[i]["ring_id"] >= 0 else 1
        for k in range(count):
            # Ring members deliberately reuse a small pool of directors.
            if companies[i]["ring_id"] >= 0:
                din = f"{10000000 + (companies[i]['ring_id'] * 7 + k) % max(1, n_directors):08d}"
            else:
                din = f"{rng.randrange(10000000, 99999999):08d}"
            if din in seen_dirs:
                continue
            seen_dirs.add(din)
            directors.append({
                "din": din,
                "name": f"Director {din}",
                "pan_hash": hashlib.sha256(din.encode()).hexdigest()[:16],
                "company_cin": companies[i]["cin"],
            })

    addresses: List[Dict[str, Any]] = []
    for i in range(n):
        if companies[i]["ring_id"] >= 0:
            key = f"ring-{companies[i]['ring_id']}"
        else:
            key = f"addr-{rng.randrange(n_addresses)}"
        addresses.append({
            "normalized_address": key,
            "raw_address": f"{key}, Mumbai, Maharashtra",
            "state": "Maharashtra",
            "company_cin": companies[i]["cin"],
        })

    transactions: List[Dict[str, Any]] = []
    for k, (a, b) in enumerate(edges):
        transactions.append({
            "id": f"scale-txn-{seed}-{k}",
            "invoice_no": f"SCALE-INV-{seed}-{k}",
            "amount": float(rng.randrange(10_000, 5_000_000)),
            "seller_cin": companies[a]["cin"],
            "buyer_cin": companies[b]["cin"],
            "in_ring": 1 if (a in ring_members and b in ring_members
                             and ring_members[a] == ring_members[b]) else 0,
        })

    return {
        "companies": companies,
        "directors": directors,
        "addresses": addresses,
        "transactions": transactions,
        "stats": {
            "companies": len(companies),
            "directors": len(directors),
            "addresses": len(addresses),
            "transactions": len(transactions),
            "rings": ring_count,
            "ring_members": len(ring_members),
        },
    }


# --- Bulk load ---------------------------------------------------------------

_CYPHER_COMPANIES = """
UNWIND $rows AS r
MERGE (c:Company {cin: r.cin})
SET c.gstin = r.gstin, c.name = r.name, c.nic_code = r.nic_code,
    c.paid_up_capital = r.paid_up_capital, c.status = r.status,
    c.id = coalesce(c.id, r.cin), c.scale_tag = $tag
"""

_CYPHER_DIRECTORS = """
UNWIND $rows AS r
MERGE (d:Director {din: r.din})
SET d.name = r.name, d.pan_hash = r.pan_hash, d.id = coalesce(d.id, r.din)
WITH d, r
MATCH (c:Company {cin: r.company_cin})
MERGE (d)-[:DIRECTOR_OF]->(c)
"""

_CYPHER_ADDRESSES = """
UNWIND $rows AS r
MERGE (a:Address {normalized_address: r.normalized_address})
SET a.raw_address = r.raw_address, a.state = r.state,
    a.id = coalesce(a.id, r.normalized_address)
WITH a, r
MATCH (c:Company {cin: r.company_cin})
MERGE (c)-[:REGISTERED_AT]->(a)
"""

_CYPHER_TXNS = """
UNWIND $rows AS r
MATCH (seller:Company {cin: r.seller_cin})
MATCH (buyer:Company {cin: r.buyer_cin})
MERGE (t:Transaction {id: r.id})
SET t.invoice_no = r.invoice_no, t.amount = r.amount, t.in_ring = r.in_ring
MERGE (seller)-[:BILLED]->(t)
MERGE (t)-[:BILLED_TO]->(buyer)
"""


def _chunks(seq: List[Any], size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def load_rows(rows: Dict[str, List[Dict[str, Any]]], batch: int = 5000,
              tag: str = SCALE_TAG) -> Dict[str, float]:
    """Load row sets with batched UNWIND writes. Returns per-stage seconds."""
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    timings: Dict[str, float] = {}
    specs = [
        ("companies", _CYPHER_COMPANIES, rows["companies"]),
        ("directors", _CYPHER_DIRECTORS, rows["directors"]),
        ("addresses", _CYPHER_ADDRESSES, rows["addresses"]),
        ("transactions", _CYPHER_TXNS, rows["transactions"]),
    ]
    with driver.session() as session:
        for name, cypher, data in specs:
            t0 = time.perf_counter()
            for chunk in _chunks(data, batch):
                session.run(cypher, rows=chunk, tag=tag).consume()
            timings[name] = time.perf_counter() - t0
    driver.close()
    timings["total"] = sum(timings.values())
    return timings


def wipe_scale_data(tag: str = SCALE_TAG) -> None:
    """Remove all nodes created by the scale test (matched by tag/id prefix)."""
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session() as session:
        session.run(
            "MATCH (c:Company {scale_tag: $tag}) DETACH DELETE c", tag=tag
        ).consume()
        session.run(
            "MATCH (t:Transaction) WHERE t.id STARTS WITH 'scale-txn-' DETACH DELETE t"
        ).consume()
        session.run(
            "MATCH (d:Director) WHERE d.name STARTS WITH 'Director ' "
            "AND NOT (d)-[:DIRECTOR_OF]->() DETACH DELETE d"
        ).consume()
        session.run(
            "MATCH (a:Address) WHERE a.raw_address CONTAINS 'Mumbai, Maharashtra' "
            "AND NOT ()-[:REGISTERED_AT]->(a) DETACH DELETE a"
        ).consume()
    driver.close()


def count_graph() -> Dict[str, int]:
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    out: Dict[str, int] = {}
    with driver.session() as session:
        for label in ("Company", "Director", "Address", "Transaction"):
            rec = session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()
            out[label] = rec["c"]
    driver.close()
    return out


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--nodes", type=int, required=True, help="Company nodes")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--batch", type=int, default=5000)
    p.add_argument("--load", action="store_true", help="Write to Neo4j")
    p.add_argument("--wipe", action="store_true", help="Delete scale data first")
    args = p.parse_args(argv)

    if args.wipe:
        print("[scale] wiping previous scale data ...", flush=True)
        wipe_scale_data()

    t0 = time.perf_counter()
    rows = build_rows(args.nodes, seed=args.seed)
    gen_s = time.perf_counter() - t0
    print(f"[scale] generated in {gen_s:.2f}s: {rows['stats']}", flush=True)

    if args.load:
        timings = load_rows(rows, batch=args.batch)
        print(f"[scale] loaded in {timings['total']:.2f}s: {timings}", flush=True)
        print(f"[scale] graph counts: {count_graph()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
