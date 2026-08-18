"""Phase 3 inference: load the persisted checkpoint, score the live graph,
and write Company.risk_score back to Neo4j (Implementation Plan Phase 3).

The model loads lazily and caches; absence of torch or the checkpoint is
handled gracefully so the rest of the app keeps working (feature flag).
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CHECKPOINT_PATH = os.getenv("GNN_CHECKPOINT_PATH", "/app/models/gnn_risk_v1.pt")

_model: Optional[Any] = None
_checkpoint: Optional[Dict[str, Any]] = None

try:  # torch is optional: the stack works without the GNN layer
    import torch
except ImportError:
    torch = None

_scoring_lock: Optional[asyncio.Lock] = None


def is_available() -> bool:
    return torch is not None and os.path.exists(CHECKPOINT_PATH)


def _load():
    global _model, _checkpoint
    if not is_available():
        return False
    if _model is None:
        from .model import GraphSAGE

        _checkpoint = torch.load(CHECKPOINT_PATH, map_location="cpu")
        _model = GraphSAGE(in_dim=len(_checkpoint["feature_cols"]))
        _model.load_state_dict(_checkpoint["model_state"])
        _model.eval()
        logger.info("GNN checkpoint loaded: %s", CHECKPOINT_PATH)
    return True


def model_meta() -> Optional[Dict[str, Any]]:
    if not _load():
        return None
    metrics = {}
    if os.path.exists(os.path.join(os.path.dirname(CHECKPOINT_PATH), "gnn_metrics.json")):
        with open(os.path.join(os.path.dirname(CHECKPOINT_PATH), "gnn_metrics.json")) as f:
            metrics = json.load(f)
    return {"version": _checkpoint.get("version"), "feature_cols": _checkpoint.get("feature_cols"), "metrics": metrics}


async def predict_and_writeback(session) -> Dict[str, Any]:
    """Score all companies and write Company.risk_score = GNN score * 100."""
    if not _load():
        raise RuntimeError(
            "GNN layer unavailable: install torch and train a checkpoint "
            "(python -m app.services.gnn.train)"
        )

    from . import features as feat
    from .model import build_adjacency

    data = await feat.extract_graph(session)
    companies = data["companies"]
    n = len(companies)
    if n == 0:
        return {"scored": 0, "error": "no companies in graph"}

    idx = {c["id"]: i for i, c in enumerate(companies)}
    edges = [(idx[s], idx[d]) for s, d in data["edges"] if s in idx and d in idx]
    x = torch.tensor([c["_features"] for c in companies], dtype=torch.float32)
    a_norm = build_adjacency(edges, n)

    with torch.no_grad():
        scores = torch.sigmoid(_model(x, a_norm)).tolist()

    written = 0
    for c, s in zip(companies, scores):
        risk = round(min(max(s * 100.0, 0.0), 100.0), 1)
        await session.run(
            "MATCH (c:Company {id: $id}) SET c.risk_score = $risk, c.risk_source = 'gnn_v1', c.updated_at = datetime()",
            id=c["id"], risk=risk,
        )
        written += 1
    return {"scored": written, "source": "gnn_v1", "model": model_meta()}


async def _scores_stale(session) -> bool:
    """True if any company is missing a gnn_v1 score (fresh load, wipe+reload,
    or a loader run after startup)."""
    result = await session.run(
        "MATCH (c:Company) WHERE c.risk_score IS NULL OR c.risk_source <> 'gnn_v1' "
        "RETURN count(c) AS stale"
    )
    rec = await result.single()
    return bool(rec and rec["stale"] > 0)


async def ensure_scored(session) -> Dict[str, Any]:
    """Self-healing demo guard: if the GNN checkpoint exists but the graph's
    companies have no gnn_v1 scores yet (e.g. after a wipe+reload), run the
    structural analytics that materialize pagerank/betweenness/community and
    FraudCycle artifacts, then score everything and write risk_score back.

    Idempotent + concurrency-safe: once every company carries a gnn_v1 score
    the check short-circuits, so normal requests are never slowed down."""
    global _scoring_lock
    if not is_available():
        return {"scored": 0, "reason": "checkpoint_missing"}
    if _scoring_lock is None:
        _scoring_lock = asyncio.Lock()
    async with _scoring_lock:
        if not await _scores_stale(session):
            return {"scored": 0, "reason": "up_to_date"}
        from ..graph_service import run_structural_analytics

        await run_structural_analytics(session)
        summary = await predict_and_writeback(session)
        logger.info("ensure_scored: re-scored %s companies", summary.get("scored"))
        return summary