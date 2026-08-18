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


def generate_graph(
    seed: int,
    n_companies: int = 24,
    n_rings: int = 2,
    ring_min: int = 3,
    ring_max: int = 5,
    noise_edges: float = 0.3,
) -> Dict[str, object]:
    """Emit the same 8 feature columns as features.FEATURE_COLS so the
    pretrained GraphSAGE transfers to the live graph: degree, pagerank,
    betweenness, puc_log, cycle_member, shared_director, shared_address,
    community_share."""
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
        feats.append([deg, pagerank, betweenness, puc_log, cycle_member,
                      shared_director, shared_address, community_share])

    x = torch.tensor(feats, dtype=torch.float32)
    a_norm = build_adjacency(edges, n)
    y = torch.tensor(labels, dtype=torch.float32)
    return {"x": x, "a_norm": a_norm, "y": y, "edges": edges, "n": n}


def generate_benchmark(n_graphs: int = 40, **kwargs) -> List[Dict[str, object]]:
    return [generate_graph(seed=i, **kwargs) for i in range(n_graphs)]


def split_benchmark(graphs: List[Dict[str, object]], frac: float = 0.8):
    cut = int(len(graphs) * frac)
    return graphs[:cut], graphs[cut:]