"""Phase 3 tests: GNN layer (Implementation Plan Phase 3, TRD §9 metrics).
Pure-torch units run anywhere; the live test runs the predict write-back
against the running Neo4j stack.

Usage: docker compose exec api pytest tests -q
"""

import asyncio

import pytest

from app.services.gnn import features, model as gnn_model, synthetic


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


# --- Feature-column alignment (regression) ---
#
# The pretrained model is applied to the live graph, so the generator's
# columns, the live extractor's columns and the trained checkpoint's columns
# must all agree. When B1/B2 added features without retraining, the committed
# checkpoint still expected 8 columns while the extractor produced 10, which
# crashed every endpoint that calls ensure_scored(). These tests make that
# drift visible in CI instead of at runtime.

def test_generator_columns_match_live_extractor():
    """The generator must emit exactly the columns the live extractor
    produces -- same names, same order (train.py asserts this too)."""
    assert synthetic.GENERATOR_FEATURE_COLS == features.FEATURE_COLS


def test_generator_emits_one_column_per_declared_feature():
    g = synthetic.generate_graph(seed=3, n_companies=12, n_rings=1)
    assert g["x"].shape[1] == len(features.FEATURE_COLS)
    assert g["feature_cols"] == features.FEATURE_COLS


def test_checkpoint_columns_match_live_extractor():
    """The committed checkpoint must be trained on the columns the live
    extractor produces. Otherwise inference silently feeds the model a
    misaligned feature matrix."""
    from app.services.gnn import predict as gnn_predict

    assert gnn_predict.is_available(), "checkpoint must exist"
    ck = gnn_model.torch.load(gnn_predict.CHECKPOINT_PATH, map_location="cpu", weights_only=True)
    assert list(ck["feature_cols"]) == features.FEATURE_COLS, (
        "checkpoint columns differ from the live extractor; retrain with "
        "python -m app.services.gnn.train"
    )


def test_feature_matrix_selects_columns_by_name():
    """Inference selects the checkpoint's columns by NAME, so an unknown
    column is 0.0 rather than a misaligned value."""
    from app.services.gnn import predict as gnn_predict

    companies = [
        {"_feature_map": {"degree": 0.5, "eway_mismatch": 0.25}},
        {"_feature_map": {"degree": 1.0, "eway_mismatch": 0.75}},
    ]
    m = gnn_predict.build_feature_matrix(companies, ["degree", "eway_mismatch"])
    assert m == [[0.5, 0.25], [1.0, 0.75]]

    # A column the extractor no longer produces is zero-filled, not shifted.
    m2 = gnn_predict.build_feature_matrix(companies, ["degree", "gone"])
    assert m2 == [[0.5, 0.0], [1.0, 0.0]]

    # Column ORDER follows the requested list, not the map's insertion order.
    m3 = gnn_predict.build_feature_matrix(companies, ["eway_mismatch", "degree"])
    assert m3 == [[0.25, 0.5], [0.75, 1.0]]


# --- Live: GNN predict write-back ---

def test_predict_writeback_live():
    from app.deps import get_neo4j_session
    from app.services.gnn import predict as gnn_predict

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
    from app.services.gnn import predict as gnn_predict

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


# --- Live: GET /analytics/gnn/model (active model_versions row) ---

def test_get_gnn_model_live():
    """The endpoint must report the currently active model_versions row,
    matching the registry in Postgres exactly."""
    import httpx
    from sqlalchemy import text as _text

    from app.deps import async_session_maker

    async def _active_row():
        async with async_session_maker() as db:
            res = await db.execute(_text(
                "SELECT id::text AS id, version_tag, is_active FROM model_versions "
                "WHERE is_active = true ORDER BY deployed_at DESC LIMIT 1"
            ))
            return res.mappings().first()

    row = _run(_active_row())
    assert row is not None, "seed migration 010 must provide an active model_versions row"

    r = httpx.get("http://localhost:8000/api/v1/analytics/gnn/model", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["is_active"] is True
    assert body["id"] == row["id"]
    assert body["version_tag"] == row["version_tag"]
    assert "checkpoint_path" in body
    assert "checkpoint_available" in body
