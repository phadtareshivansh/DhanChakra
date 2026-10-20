"""Leakage guards for the model benchmark (api/benchmarks/run_benchmark.py).

Two independent guards:

1. **Signature guard** — the headline feature builder must be callable with ONLY
   (edges, n), so it structurally cannot receive labels, ring membership, or the
   generator's feature matrix. Also asserts the benchmark never reads
   ``cycle_member`` for the headline view.

2. **Label-shuffle guard** — permute the labels within each graph, retrain the
   learned models, and assert they collapse to chance on test (AUC-ROC ~0.5,
   AUC-PR ~prevalence). If they do not, real leakage remains and the test fails
   loudly with the observed numbers.

Run: docker compose exec api pytest tests/test_benchmark_leakage.py -q
"""

import inspect
import sys

import numpy as np
import pytest

sys.path.insert(0, "/benchmarks")

import run_benchmark as rb  # noqa: E402


# --- Guard 1: signature / input isolation -----------------------------------

def test_build_features_signature_is_edges_and_n_only():
    params = list(inspect.signature(rb.build_features).parameters)
    assert params == ["edges", "n"], (
        f"build_features must take only (edges, n) so it cannot see labels; got {params}"
    )


def test_floor_features_signature_is_edges_and_n_only():
    params = list(inspect.signature(rb.floor_features).parameters)
    assert params == ["edges", "n"], params


def test_cycle_detection_signature_is_edges_and_n_only():
    params = list(inspect.signature(rb.recompute_cycle_members).parameters)
    assert params == ["edges", "n"], params


def test_headline_view_excludes_cycle_member():
    """The generator's label-copy column must not be in the headline columns."""
    assert "cycle_member" not in rb.EDGE_FEATURE_COLS
    assert "cycle_member" not in rb.FLOOR_FEATURE_COLS
    assert "cycle_member" in rb.GENERATOR_FEATURE_COLS  # it exists, just quarantined


def test_build_features_is_deterministic_and_label_free():
    """Same edges -> same features, regardless of any label vector."""
    g = rb.make_graph(12345)
    a = rb.build_features(g["edges"], g["n"])
    b = rb.build_features(g["edges"], g["n"])
    assert np.array_equal(a, b)
    assert a.shape == (g["n"], len(rb.EDGE_FEATURE_COLS))


def test_rule_baseline_does_not_copy_the_label():
    """On the generator, cycle_member is an exact label copy; the rule recomputes
    cycles from edges, so it must NOT be a perfect classifier."""
    g = rb.make_graph(0)
    y = g["y"].numpy().astype(int)
    scores = rb.rule_scores(g["edges"], g["n"])
    exact = np.array_equal((scores >= 0.5).astype(int), y)
    assert not exact, (
        "rule baseline reproduced the label exactly - it is reading cycle_member"
    )


# --- Guard 2: label-shuffle collapse ----------------------------------------

@pytest.fixture(scope="module")
def shuffle_report():
    return rb.label_shuffle_check(seed=1, n_graphs=20)


@pytest.mark.parametrize("view", ["edge", "floor"])
def test_label_shuffle_collapses_to_chance(view, shuffle_report):
    rec = shuffle_report[view]
    assert "note" not in rec, rec["note"]
    prevalence = rec["prevalence"]
    for model in ("logistic_regression", "gradient_boosting"):
        auc_roc = rec[model]["auc_roc"]
        auc_pr = rec[model]["auc_pr"]
        assert 0.30 <= auc_roc <= 0.70, (
            f"LEAKAGE: {view}/{model} AUC-ROC={auc_roc:.3f} after label shuffle "
            f"(expected ~0.5). Features still encode the label."
        )
        assert auc_pr <= max(3 * prevalence, prevalence + 0.15), (
            f"LEAKAGE: {view}/{model} AUC-PR={auc_pr:.3f} vs prevalence "
            f"{prevalence:.3f} after label shuffle."
        )


def test_shuffle_reports_are_present(shuffle_report):
    for view in ("edge", "floor", "leak"):
        assert view in shuffle_report, f"missing shuffle report for view {view}"
