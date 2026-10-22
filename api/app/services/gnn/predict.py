"""Phase 3 inference: load the persisted checkpoint, score the live graph,
and write Company.risk_score back to Neo4j (Implementation Plan Phase 3).

Two backends are supported:
- torch, when the training dependency and the .pt checkpoint are present;
- numpy, using a small .npz exported from the same checkpoint. The Render
  production image ships only numpy, so it avoids torch's import/RAM cost.

The model loads lazily and caches; absence of both backends is handled
gracefully so the rest of the app keeps working (feature flag).
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, Optional

import numpy as np

from ...config import settings

logger = logging.getLogger(__name__)

CHECKPOINT_PATH = settings.gnn_checkpoint_file
NPZ_PATH = os.path.splitext(CHECKPOINT_PATH)[0] + ".npz"

_model: Optional[Any] = None
_checkpoint: Optional[Dict[str, Any]] = None
_np_weights: Optional[Dict[str, np.ndarray]] = None
_np_meta: Optional[Dict[str, Any]] = None

try:  # torch is optional: the numpy backend keeps the GNN layer working
    import torch
except ImportError:
    torch = None

_scoring_lock: Optional[asyncio.Lock] = None


def _backend() -> Optional[str]:
    """Which inference backend to use, or None when no weights exist."""
    preference = (settings.gnn_backend or "auto").strip().lower()
    has_torch = torch is not None and os.path.exists(CHECKPOINT_PATH)
    has_numpy = os.path.exists(NPZ_PATH)
    if preference == "numpy":
        return "numpy" if has_numpy else None
    if preference == "torch":
        return "torch" if has_torch else None
    if has_torch:
        return "torch"
    if has_numpy:
        return "numpy"
    return None


def is_available() -> bool:
    return _backend() is not None


def _load_torch() -> bool:
    global _model, _checkpoint
    if _model is None:
        from .model import GraphSAGE

        # weights_only=True is safe here: train.py saves a dict holding the
        # model's tensor state_dict plus plain primitives (feature_cols /
        # version / trained_at), all of which the restricted unpickler allows.
        # Passing it explicitly drops torch's FutureWarning (the default flips
        # to True in a future release) and fails closed if a checkpoint ever
        # starts carrying arbitrary pickled objects.
        _checkpoint = torch.load(CHECKPOINT_PATH, map_location="cpu", weights_only=True)
        _model = GraphSAGE(in_dim=len(_checkpoint["feature_cols"]))
        _model.load_state_dict(_checkpoint["model_state"])
        _model.eval()
        logger.info("GNN torch checkpoint loaded: %s", CHECKPOINT_PATH)
    return True


def _load_numpy() -> bool:
    global _np_weights, _np_meta
    if _np_weights is None:
        with np.load(NPZ_PATH, allow_pickle=False) as data:
            _np_weights = {
                "conv1_weight": data["conv1_weight"].astype(np.float32),
                "conv1_bias": data["conv1_bias"].astype(np.float32),
                "conv2_weight": data["conv2_weight"].astype(np.float32),
                "conv2_bias": data["conv2_bias"].astype(np.float32),
            }
            _np_meta = {
                "version": str(data["version"].item()),
                "trained_at": str(data["trained_at"].item()),
                "feature_cols": json.loads(str(data["feature_cols"].item())),
            }
        logger.info("GNN numpy weights loaded: %s", NPZ_PATH)
    return True


def _load() -> bool:
    backend = _backend()
    if backend == "torch":
        return _load_torch()
    if backend == "numpy":
        return _load_numpy()
    return False


def _metrics() -> Dict[str, Any]:
    metrics_path = os.path.join(
        os.path.dirname(CHECKPOINT_PATH), settings.gnn_metrics_filename
    )
    if not os.path.exists(metrics_path):
        return {}
    try:
        with open(metrics_path) as f:
            return json.load(f)
    except Exception:
        return {}


def model_meta() -> Optional[Dict[str, Any]]:
    if not _load():
        return None
    if _backend() == "numpy":
        return {**_np_meta, "metrics": _metrics(), "backend": "numpy"}
    return {
        "version": _checkpoint.get("version"),
        "trained_at": _checkpoint.get("trained_at"),
        "feature_cols": _checkpoint.get("feature_cols"),
        "metrics": _metrics(),
        "backend": "torch",
    }


def build_feature_matrix(companies: list, cols: list) -> "Any":
    """Select `cols` (by name) out of the extracted companies' feature maps.

    A column the extractor does not produce is 0.0. This is what makes an
    old checkpoint usable against a newer feature set instead of crashing on
    a shape mismatch."""
    return [
        [float((c.get("_feature_map") or {}).get(col, 0.0)) for col in cols]
        for c in companies
    ]


def _build_adjacency_numpy(edges: list, n: int) -> np.ndarray:
    """Row-normalized directed adjacency (self-loops included), mirroring
    gnn.model.build_adjacency exactly."""
    a = np.zeros((n, n), dtype=np.float32)
    for src, dst in edges:
        if 0 <= src < n and 0 <= dst < n:
            a[src, dst] += 1.0
    a += np.eye(n, dtype=np.float32)
    row_sum = np.clip(a.sum(axis=1, keepdims=True), 1.0, None)
    return a / row_sum


def _forward_numpy(x: np.ndarray, a_norm: np.ndarray) -> np.ndarray:
    """GraphSAGE forward pass without torch. Dropout is identity in eval mode."""
    assert _np_weights is not None
    h = np.concatenate([x, a_norm @ x], axis=1)
    h = h @ _np_weights["conv1_weight"].T + _np_weights["conv1_bias"]
    h = np.maximum(h, 0.0)
    logits = (
        np.concatenate([h, a_norm @ h], axis=1)
        @ _np_weights["conv2_weight"].T
        + _np_weights["conv2_bias"]
    )
    logits = logits.squeeze(-1)
    return 1.0 / (1.0 + np.exp(-logits))


async def predict_and_writeback(session) -> Dict[str, Any]:
    """Score all companies and write Company.risk_score = GNN score * 100."""
    backend = _backend()
    if backend is None or not _load():
        raise RuntimeError(
            "GNN layer unavailable: train a checkpoint (python -m "
            "app.services.gnn.train) and either install torch or export "
            "models/gnn_risk_v1.npz with scripts/export_gnn_npz.py"
        )

    from . import features as feat

    data = await feat.extract_graph(session)
    companies = data["companies"]
    n = len(companies)
    if n == 0:
        return {"scored": 0, "error": "no companies in graph"}

    idx = {c["id"]: i for i, c in enumerate(companies)}
    edges = [(idx[s], idx[d]) for s, d in data["edges"] if s in idx and d in idx]

    # Build the input matrix from the columns THIS checkpoint was trained on,
    # selected by name. The live extractor may expose more (or fewer) columns
    # than the checkpoint knows about -- e.g. features were added after the
    # model was trained. Positional slicing would silently misalign the
    # features (and used to crash the whole API with a shape mismatch); by
    # name, an unknown column is simply 0.0 and a new column is ignored until
    # the model is retrained.
    meta = _np_meta if backend == "numpy" else _checkpoint
    cols = list((meta or {}).get("feature_cols") or feat.FEATURE_COLS)
    unknown = [c for c in cols if c not in feat.FEATURE_COLS]
    if unknown:
        logger.warning(
            "checkpoint expects columns the extractor no longer produces: %s "
            "(they are treated as 0.0; retrain to pick them up)",
            ", ".join(unknown),
        )
    missing = [c for c in feat.FEATURE_COLS if c not in cols]
    if missing:
        logger.info(
            "checkpoint does not use these live features: %s",
            ", ".join(missing),
        )

    x_list = build_feature_matrix(companies, cols)
    if backend == "numpy":
        x = np.asarray(x_list, dtype=np.float32)
        a_norm = _build_adjacency_numpy(edges, n)
        scores = _forward_numpy(x, a_norm).tolist()
    else:
        from .model import build_adjacency

        x = torch.tensor(x_list, dtype=torch.float32)
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
