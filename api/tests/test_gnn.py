"""Phase 3 tests: GNN layer (Implementation Plan Phase 3, TRD §9 metrics).
Pure-torch units run anywhere; the live test runs the predict write-back
against the running Neo4j stack.

Usage: docker exec dhanchakra-api pytest /tmp/tests/test_gnn.py -q
"""

import asyncio
import os
import sys

import pytest

sys.path.insert(0, "/app/app")

from services.gnn import features, model as gnn_model, synthetic


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# --- Metrics (TRD §9): F1 / AUC-PR / recall@k ---

def test_evaluate_perfect():
    scores = [3.0, 2.0, 1.0, -1.0, -2.0]
    labels = [1, 1, 1, 0, 0]
    m = gnn_model.evaluate(
        gnn_model.torch.tensor(scores, dtype=gnn_model.torch.float32),
        gnn_model.torch.tensor(labels, dtype=gnn_model.torch.float32),
    )
    assert m["f1"] == 1.0
    assert m["auc_pr"] == 1.0
    assert m["recall_at_k"] == 1.0


def test_evaluate_all_negative():
    labels = [0, 0, 0]
    scores = [-1.0, -2.0, -3.0]
    m = gnn_model.evaluate(
        gnn_model.torch.tensor(scores, dtype=gnn_model.torch.float32),
        gnn_model.torch.tensor(labels, dtype=gnn_model.torch.float32),
    )
    assert m["f1"] == 0.0


def test_evaluate_recall_at_k():
    labels = [1, 0, 0, 1]
    scores = [2.0, 1.0, 0.5, -1.0]  # only 1 of 2 positives in top-2
    m = gnn_model.evaluate(
        gnn_model.torch.tensor(scores, dtype=gnn_model.torch.float32),
        gnn_model.torch.tensor(labels, dtype=gnn_model.torch.float32),
        k=2,
    )
    assert m["recall_at_k"] == 0.5


# --- Model shape + training loop ---

def test_graphsage_shapes():
    n, d = 10, 8
    x = gnn_model.torch.randn(n, d)
    a = gnn_model.build_adjacency([(i, (i + 1) % n) for i in range(n)], n)
    m = gnn_model.GraphSAGE(in_dim=d)
    logits = m(x, a)
    assert tuple(logits.shape) == (n,)
    assert a.shape == (n, n)
    assert abs(a.sum(dim=1).min().item() - 1.0) < 1e-6


def test_train_synthetic_smoke():
    g = synthetic.generate_graph(seed=7, n_companies=16, n_rings=1)
    m, losses = gnn_model.train_model(g["x"], g["a_norm"], g["y"], epochs=30)
    assert len(losses) == 30
    m.eval()
    with gnn_model.torch.no_grad():
        out = gnn_model.torch.sigmoid(m(g["x"], g["a_norm"]))
    ring_ids = [i for i in range(16) if g["y"][i] == 1]
    clean_ids = [i for i in range(16) if g["y"][i] == 0]
    assert out[ring_ids].mean() > out[clean_ids].mean()


# --- Feature extraction + weak labels ---

def test_weak_labels_threshold():
    comps = [
        {"cycle_member": True, "risk_score": 10.0},
        {"cycle_member": False, "risk_score": 55.0},
        {"cycle_member": False, "risk_score": 5.0},
    ]
    labels = features.weak_labels(comps, threshold=40.0)
    assert labels == [1, 1, 0]


# --- Live: GNN predict write-back ---

def test_predict_writeback_live():
    from app.deps import get_neo4j_session
    from services.gnn import predict as gnn_predict

    assert gnn_predict.is_available(), "checkpoint must exist (run python -m app.services.gnn.train)"

    async def _check():
        async with get_neo4j_session() as session:
            summary = await gnn_predict.predict_and_writeback(session)
            assert summary["scored"] >= 6
            assert summary["source"] == "gnn_v1"

            res = await session.run("""
            MATCH (c:Company)
            WHERE c.risk_source = 'gnn_v1'
            RETURN count(c) AS n, min(c.risk_score) AS lo, max(c.risk_score) AS hi
            """)
            row = await res.single()
            assert row["n"] >= 6
            assert 0.0 <= row["lo"] <= row["hi"] <= 100.0

    _run(_check())

def test_ensure_scored_idempotent_live():
    """ensure_scored must never error and must short-circuit once every
    company carries a gnn_v1 score (no double scoring)."""
    from app.deps import get_neo4j_session
    from services.gnn import predict as gnn_predict

    async def _check():
        async with get_neo4j_session() as session:
            first = await gnn_predict.ensure_scored(session)
            assert "scored" in first and "reason" in first

            res = await session.run("""
            MATCH (c:Company) WHERE c.risk_score IS NULL OR c.risk_source <> 'gnn_v1'
            RETURN count(c) AS stale
            """)
            assert (await res.single())["stale"] == 0

            second = await gnn_predict.ensure_scored(session)
            assert second["reason"] == "up_to_date"

    _run(_check())
