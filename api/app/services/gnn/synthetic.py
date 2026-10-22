"""AML-style synthetic benchmark generator (Phase 3 data prep).

Each graph: a few companies, some organized into invoice loops (fraud rings,
mirroring the seed data), plus clean companies with random transactions.
Ring members share directors/addresses to mimic shell-company patterns.
"""

import math
import random
from typing import Dict, List, Tuple

import torch

from .model import build_adjacency


# The columns this generator emits. MUST stay identical (same names, same
# order) to features.FEATURE_COLS, otherwise the pretrained GraphSAGE cannot
# be applied to the live graph. train.py asserts the two lists match before
# it trains, and api/tests/test_gnn.py asserts it too.
GENERATOR_FEATURE_COLS = [
    "degree",           # normalized invoice degree
    "pagerank",
    "betweenness",
    "puc_log",          # log1p(paid_up_capital) normalized
    "cycle_member",     # 1 if in a materialized FraudCycle
    "shared_director",  # normalized count
    "shared_address",   # normalized count
    "community_share",  # fraction of companies in same louvain community
    "eway_mismatch",    # high-value invoice with no matching e-Way Bill movement
    "burst_indicator",  # entity involved in a detected burst window
]


def generate_graph(
    seed: int,
    n_companies: int = 24,
    n_rings: int = 2,
    ring_min: int = 3,
    ring_max: int = 5,
    noise_edges: float = 0.3,
) -> Dict[str, object]:
    """Emit the same feature columns as features.FEATURE_COLS so the
    pretrained GraphSAGE transfers to the live graph.

    Leakage note: the first 8 columns are a direct function of the generator's
    `in_ring` flag (`cycle_member` is an exact copy), so this matrix cannot be
    used for honest evaluation -- the benchmark quarantines it as a
    "with-leak" sanity view (see api/benchmarks/run_benchmark.py).

    The two later columns (eway_mismatch, burst_indicator) are deliberately
    NOISY rather than exact: a quarter of ring members have no e-Way Bill gap
    at all, and clean companies occasionally have a burst window. They stay
    correlated with ring membership without becoming a second label clone.
    """
    rng = random.Random(seed)
    labels = [0] * n_companies
    edges: List[Tuple[int, int]] = []
    ring_members: List[int] = []
    used = 0
    for _ in range(n_rings):
        size = rng.randint(ring_min, ring_max)
        members = list(range(used, used + size))
        ring_members += members
        used += size
        for i in range(size):
            edges.append((members[i], members[(i + 1) % size]))
            if rng.random() < noise_edges:
                edges.append((members[(i + 1) % size], members[i]))

    for i in ring_members:
        labels[i] = 1

    for i in range(n_companies):
        if i in ring_members:
            continue
        for _ in range(rng.randint(1, 4)):
            j = rng.randrange(n_companies)
            if j != i:
                edges.append((i, j))

    n = n_companies
    max_deg = max([sum(1 for e in edges if e[0] == i) for i in range(n)] or [1])
    max_puc = max([(i % 5 + 1) for i in range(n)] or [1])

    # Simulated louvain: ring members share one community; clean nodes split
    community_of: Dict[int, int] = {}
    comm_sizes: Dict[int, int] = {}
    for i in range(n):
        cid = 0 if i in ring_members else i
        community_of[i] = cid
        comm_sizes[cid] = comm_sizes.get(cid, 0) + 1

    feats = []
    for i in range(n):
        in_ring = i in ring_members
        deg = sum(1 for e in edges if e[0] == i) / max_deg
        pagerank = rng.uniform(0.05, 0.15) + (0.3 if in_ring else 0.0)
        betweenness = rng.uniform(0.0, 0.05) + (0.2 if in_ring else 0.0)
        puc = (i % 5 + 1) / max_puc
        puc_log = math.log1p((i % 5 + 1)) / math.log1p(max_puc)
        cycle_member = 1.0 if in_ring else 0.0
        shared_director = rng.uniform(0.5, 0.8) if in_ring else rng.uniform(0.0, 0.1)
        shared_address = rng.uniform(0.4, 0.7) if in_ring else rng.uniform(0.0, 0.1)
        community_share = comm_sizes[community_of[i]] / n
        # e-Way Bill gap: ring members invoice each other heavily, so some of
        # their high-value invoices have no matching movement record. A
        # quarter of ring members have none, so this column is correlated with
        # the label but is NOT a copy of it.
        if in_ring:
            eway_mismatch = 0.0 if rng.random() < 0.25 else rng.uniform(0.5, 1.0)
        else:
            eway_mismatch = rng.uniform(0.0, 0.25) if rng.random() < 0.2 else 0.0
        # Burst: dense reciprocal traffic trips the rolling-window burst
        # detector. Rare for clean companies, common but not universal for
        # ring members.
        burst_indicator = 1.0 if rng.random() < (0.6 if in_ring else 0.08) else 0.0
        feats.append([deg, pagerank, betweenness, puc_log, cycle_member,
                      shared_director, shared_address, community_share,
                      eway_mismatch, burst_indicator])

    x = torch.tensor(feats, dtype=torch.float32)
    a_norm = build_adjacency(edges, n)
    y = torch.tensor(labels, dtype=torch.float32)
    return {"x": x, "a_norm": a_norm, "y": y, "edges": edges, "n": n,
            "feature_cols": list(GENERATOR_FEATURE_COLS)}


def generate_benchmark(n_graphs: int = 40, **kwargs) -> List[Dict[str, object]]:
    return [generate_graph(seed=i, **kwargs) for i in range(n_graphs)]


def split_benchmark(graphs: List[Dict[str, object]], frac: float = 0.8):
    cut = int(len(graphs) * frac)
    return graphs[:cut], graphs[cut:]