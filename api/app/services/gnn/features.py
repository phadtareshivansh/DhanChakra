"""Node feature + weak-label extraction from the live Neo4j graph (Phase 3
data prep). Structural features come from Phase 1 write-backs (pagerank,
betweenness, community_id) plus local red flags (cycle membership, shared
directors/addresses) and balance-sheet signal (paid-up capital).
"""

from typing import Any, Dict, List, Optional

from ...config import settings


FEATURE_COLS = [
    "degree",           # normalized invoice degree
    "pagerank",
    "betweenness",
    "puc_log",          # log1p(paid_up_capital) normalized
    "cycle_member",     # 1 if in a materialized FraudCycle
    "shared_director",  # normalized count
    "shared_address",   # normalized count
    "community_share",  # fraction of companies in same louvain community
    "eway_mismatch",    # 1 if high-value invoice has no matching e-Way Bill movement
    "burst_indicator",  # 1 if entity involved in a detected burst window
]


def _norm(v: Optional[float], scale: float) -> float:
    try:
        return float(v) / scale if scale else 0.0
    except (TypeError, ValueError):
        return 0.0


async def _live_cycle_members(session) -> set:
    """Fallback cycle detection when FraudCycle artifacts are missing (fresh
    graph). Finds ring CINs via 2- and 3-company invoice loops; mirrors
    graph_service.get_loops at demo scale."""
    member_cins = set()
    for q in [
        """MATCH (a:Company)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(b:Company),
                 (b)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(c:Company)
            WHERE c = a
            RETURN collect(DISTINCT a.cin) + collect(DISTINCT b.cin) AS cins""",
        """MATCH (a:Company)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(b:Company),
                 (b)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(c:Company),
                 (c)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(d:Company)
            WHERE d = a
            RETURN collect(DISTINCT a.cin) + collect(DISTINCT b.cin) + collect(DISTINCT c.cin) AS cins""",
    ]:
        res = await session.run(q)
        for r in await res.data():
            member_cins.update(r["cins"] or [])
    return member_cins


async def extract_graph(session) -> Dict[str, Any]:
    """Return companies, invoice edges, and per-company raw signals."""
    has_cycles = await session.run("MATCH (cy:FraudCycle) RETURN count(cy) AS n")
    if (await has_cycles.single())["n"] > 0:
        cycle_cins: Optional[set] = None
    else:
        cycle_cins = await _live_cycle_members(session)

    comps_res = await session.run("""
    MATCH (c:Company)
    OPTIONAL MATCH (c)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(n:Company)
    WITH c, count(DISTINCT n) AS degree
    OPTIONAL MATCH (c)-[:MEMBER_OF_CYCLE]->(cy:FraudCycle)
    WITH c, degree, count(cy) > 0 AS cycle_member
    OPTIONAL MATCH (c)<-[:DIRECTOR_OF]-(d:Director)-[:DIRECTOR_OF]->(other:Company)
    WHERE other <> c
    WITH c, degree, cycle_member, count(DISTINCT other) AS shared_director
    OPTIONAL MATCH (c)-[:REGISTERED_AT]->(a:Address)<-[:REGISTERED_AT]-(sameaddr:Company)
    WHERE sameaddr <> c
    WITH c, degree, cycle_member, shared_director, count(DISTINCT sameaddr) AS shared_address
    OPTIONAL MATCH (c)-[:BILLED]->(t:Transaction)
    WHERE t.amount >= $eway_thresh AND (t.eway_bill_ref IS NULL OR t.eway_bill_ref = '')
    WITH c, degree, cycle_member, shared_director, shared_address, count(DISTINCT t) AS eway_mismatch_count
    OPTIONAL MATCH (c)-[:BILLED]->(bt:Transaction)-[:BILLED_TO]->(:Company)
    OPTIONAL MATCH (:Company)-[:BILLED]->(bt2:Transaction)-[:BILLED_TO]->(c)
    WITH c, degree, cycle_member, shared_director, shared_address, eway_mismatch_count,
         count(DISTINCT bt) + count(DISTINCT bt2) AS burst_volume
    RETURN c.id AS id, c.cin AS cin, c.name AS name,
           c.risk_score AS risk_score, c.pagerank AS pagerank,
           c.betweenness AS betweenness, c.paid_up_capital AS puc,
           c.community_id AS community_id,
           degree, cycle_member, shared_director, shared_address,
           eway_mismatch_count, burst_volume
    """, eway_thresh=settings.eway_high_value_threshold)
    companies = [dict(r) for r in await comps_res.data()]

    if cycle_cins is not None:
        for c in companies:
            c["cycle_member"] = c["cin"] in cycle_cins

    edge_res = await session.run("""
    MATCH (a:Company)-[:BILLED]->(:Transaction)-[:BILLED_TO]->(b:Company)
    RETURN a.id AS src, b.id AS dst
    """)
    edges = [(r["src"], r["dst"]) for r in await edge_res.data()]

    n = len(companies)
    max_deg = max([c["degree"] or 0 for c in companies] or [1])
    max_puc = max([c["puc"] or 0 for c in companies] or [1])
    max_sd = max([c["shared_director"] or 0 for c in companies] or [1])
    max_sa = max([c["shared_address"] or 0 for c in companies] or [1])
    max_eway = max([c.get("eway_mismatch_count") or 0 for c in companies] or [1])
    max_burst = max([c.get("burst_volume") or 0 for c in companies] or [1])
    comm_sizes: Dict[Any, int] = {}
    for c in companies:
        comm_sizes[c["community_id"]] = comm_sizes.get(c["community_id"], 0) + 1

    for c in companies:
        c["_features"] = [
            _norm(c.get("degree"), max_deg),
            _norm(c.get("pagerank"), 1.0),
            _norm(c.get("betweenness"), 1.0),
            _norm(_log1p(c.get("puc")), _log1p(max_puc)),
            1.0 if c.get("cycle_member") else 0.0,
            _norm(c.get("shared_director"), max_sd),
            _norm(c.get("shared_address"), max_sa),
            comm_sizes.get(c.get("community_id"), 0) / max(n, 1),
            _norm(c.get("eway_mismatch_count"), max_eway),
            1.0 if (c.get("burst_volume") or 0) >= settings.burst_min_transactions else 0.0,
        ]

    return {"companies": companies, "edges": edges, "n": n}


def _log1p(v: Optional[float]) -> float:
    import math
    try:
        return math.log1p(max(float(v or 0), 0.0))
    except (TypeError, ValueError):
        return 0.0


def weak_labels(companies: List[Dict[str, Any]], threshold: Optional[float] = None) -> List[int]:
    """Structural weak labels: 1 if the company is in a materialized cycle or
    the heuristic risk score already exceeds the threshold (TRD §4.6).
    Defaults to the configured weak-label threshold."""
    if threshold is None:
        threshold = settings.weak_label_threshold
    labels = []
    for c in companies:
        in_cycle = bool(c.get("cycle_member"))
        risk = float(c.get("risk_score") or 0.0)
        labels.append(1 if (in_cycle or risk >= threshold) else 0)
    return labels