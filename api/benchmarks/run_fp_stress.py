"""A2 item 4 — false-positive stress test.

Builds a LEGITIMATE tight-knit supplier cluster and reports how often each model
flags it.

The cluster is deliberately benign:

  * dense internal trade (a real supply network, not a loop);
  * no closed cycles within the 3–8 hop detection range;
  * no shared directors or addresses (none is fabricated — no dataset here has
    them);
  * plausible, heterogeneous attributes.

Two shapes are generated so the result is not a single anecdote:

  * ``chain``  — a legitimate directed supply chain (A -> B -> C -> ...), no loops
  * ``star``   — one buyer purchasing from many suppliers (fan-in), no loops

Every cluster node is a TRUE NEGATIVE, so any model that flags one has produced
a false positive.

Method (this matters):
  1. Each model is trained ONCE on the real dataset (AML-default: the chosen
     dataset's own training split), the same way the headline benchmark trains.
  2. Each model's decision threshold is chosen on the real data's VALIDATION
     split — which contains genuine positives — never on the benign cluster. An
     all-negative set cannot choose an F1 threshold, so the cluster is never used
     to calibrate.
  3. The fitted model is then applied to the benign cluster (GraphSAGE using the
     cluster's own adjacency), and we report the share of cluster nodes it flags.

    python /benchmarks/run_fp_stress.py --dataset synthetic
    python /benchmarks/run_fp_stress.py --dataset amlsim
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

for candidate in ("/app", "/benchmarks"):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import numpy as np  # noqa: E402
import torch  # noqa: E402

import run_benchmark as rb  # noqa: E402
from app.services.gnn.model import GraphSAGE, build_adjacency  # noqa: E402

MODELS = ("logistic_regression", "gradient_boosting", "graphsage", "rule_only")
HIDDEN = 16
EPOCHS = 120


# ---------------------------------------------------------------------------
# The benign cluster and the validation traffic
# ---------------------------------------------------------------------------

def legit_graph(shape: str, size: int, seed: int,
                amounts: Optional[bool] = True) -> Dict[str, Any]:
    """A benign, dense supplier cluster with NO mutual edges and NO cycles."""
    rng = random.Random(seed)
    n = size
    edges: List[Tuple[int, int]] = []

    if shape == "chain":
        # Directed forward chain; the occasional skip edge keeps it dense.
        for i in range(n - 1):
            edges.append((i, i + 1))
            if i + 2 < n and rng.random() < 0.5:
                edges.append((i, i + 2))
        # A couple of cross links that are still strictly forward (no back edges,
        # therefore no directed cycle of any length).
        for _ in range(n // 6):
            a = rng.randrange(0, max(1, n - 2))
            b = rng.randrange(a + 1, n)
            edges.append((a, b))
    elif shape == "star":
        hub = 0
        for i in range(1, n):
            edges.append((i, hub))            # many suppliers -> one buyer
        for i in range(1, n - 1):
            if rng.random() < 0.4:
                edges.append((i, i + 1))      # some supplier-to-supplier trade
    else:
        raise ValueError(shape)

    # Deduplicate, drop self-loops, verify acyclicity by construction.
    edges = sorted({(a, b) for a, b in edges if a != b})
    if not edges:
        edges = [(0, 1)]
    edge_set = set(edges)
    mutual = sum(1 for (a, b) in edges if (b, a) in edge_set)
    assert mutual == 0, "stress cluster must have no mutual edges"

    amts = ([float(rng.randrange(100, 200_000)) for _ in edges] if amounts else None)
    return {"edges": edges, "n": n, "y": torch.zeros(n, dtype=torch.float32),
            "edge_amounts": amts, "x": None}


def clean_traffic(size: int, seed: int, amounts: Optional[bool] = True) -> Dict[str, Any]:
    """Ordinary validation traffic: ordinary companies, all negative, no rings."""
    rng = random.Random(seed)
    edges: List[Tuple[int, int]] = []
    for i in range(size):
        for _ in range(rng.randint(1, 3)):
            j = rng.randrange(size)
            if j != i:
                edges.append((i, j))
    edges = sorted({(a, b) for a, b in edges if a != b}) or [(0, 1)]
    amts = ([float(rng.randrange(100, 100_000)) for _ in edges] if amounts else None)
    return {"edges": edges, "n": size, "y": torch.zeros(size, dtype=torch.float32),
            "edge_amounts": amts, "x": None}


# ---------------------------------------------------------------------------
# Feature stacking
# ---------------------------------------------------------------------------

def make_stacker(dataset: str):
    """Return (stack_fn, colset) matching the dataset's headline feature view.

    The synthetic product generator has no transaction amounts, so it uses
    ``build_features``; the AML datasets use ``build_aml_features`` with the real
    aggregated amounts. This mirrors ``run_benchmark.run_seed`` exactly.
    """
    if dataset == "synthetic":
        return (lambda g: rb.build_features(g["edges"], g["n"]), rb.EDGE_FEATURE_COLS)
    return (lambda g: rb.build_aml_features(g["edges"], g["n"],
                                            amounts=g.get("edge_amounts")),
            rb.AML_FEATURE_COLS)


# ---------------------------------------------------------------------------
# GraphSAGE train-on-real / score-elsewhere
# ---------------------------------------------------------------------------

def _train_graphsage(x: torch.Tensor, a_norm: torch.Tensor, y: torch.Tensor,
                     in_dim: int, seed: int) -> GraphSAGE:
    torch.manual_seed(seed)
    model = GraphSAGE(in_dim=in_dim, hidden=HIDDEN, dropout=0.3)
    opt = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=1e-4)
    lossfn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(3.0))
    for _ in range(EPOCHS):
        model.train()
        opt.zero_grad()
        loss = lossfn(model(x, a_norm), y)
        loss.backward()
        opt.step()
    model.eval()
    return model


def _graphsage_scores(model: GraphSAGE, x: torch.Tensor,
                      a_norm: torch.Tensor) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        return torch.sigmoid(model(x, a_norm)).numpy()


def fit_graphsage_real(graph: Dict[str, Any], X: np.ndarray,
                       tr_idx: Sequence[int], va_idx: Sequence[int],
                       seed: int) -> Tuple[GraphSAGE, float]:
    """Train GraphSAGE on the real graph, threshold on the real validation split."""
    x = torch.tensor(X, dtype=torch.float32)
    a_norm = build_adjacency(graph["edges"], graph["n"])
    y = graph["y"].float()
    model = _train_graphsage(x, a_norm, y, X.shape[1], seed)
    p = _graphsage_scores(model, x, a_norm)
    yva = graph["y"].numpy().astype(int)[list(va_idx)]
    thr = rb.best_threshold(yva, p[list(va_idx)])
    return model, thr


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def run_fp_stress(dataset: str, seeds: Sequence[int], cluster_size: int,
                  k_values: Sequence[int],
                  amlworld_path: Optional[str] = None,
                  limit_rows: Optional[int] = None) -> Dict[str, Any]:
    stack, colset = make_stacker(dataset)
    out: Dict[str, Any] = {
        "dataset": dataset, "seeds": list(seeds), "cluster_size": cluster_size,
        "columns": colset, "shapes": {},
        "notes": [
            "Cluster nodes are all TRUE NEGATIVES; a flag is a false positive.",
            "No shared directors/addresses are modelled: no dataset here has them.",
            "Thresholds are chosen on the real data's validation split, never on "
            "the benign cluster.",
        ],
    }

    for shape in ("chain", "star"):
        per_seed: List[Dict[str, Any]] = []
        for seed in seeds:
            print(f"[fp-stress] {shape} seed {seed} ...", flush=True)
            cluster = legit_graph(shape, cluster_size, seed)
            Xc = stack(cluster)

            # --- Real dataset: train + validation split -----------------------
            graphs = rb.build_dataset({"name": dataset}, seed, 20,
                                      amlworld_path=amlworld_path,
                                      limit_rows=limit_rows)
            single = len(graphs) == 1
            if single:
                g = graphs[0]
                X_real = stack(g)
                tr_idx, va_idx, _ = rb.stratified_node_split(
                    g["y"].numpy().astype(int), seed)
                Xtr, ytr = X_real[tr_idx], g["y"].numpy().astype(int)[tr_idx]
                Xva, yva = X_real[va_idx], g["y"].numpy().astype(int)[va_idx]
            else:
                tr_g, va_g, _ = rb.stratified_graph_split(graphs, seed=seed)
                Xtr = np.vstack([stack(graphs[i]) for i in tr_g])
                ytr = np.concatenate([graphs[i]["y"].numpy() for i in tr_g]).astype(int)
                Xva = np.vstack([stack(graphs[i]) for i in va_g])
                yva = np.concatenate([graphs[i]["y"].numpy() for i in va_g]).astype(int)

            # --- Fit ONCE each; threshold on the real validation split --------
            lr_model = rb._lr_full_fit(Xtr, ytr, seed)
            thr_lr = rb.best_threshold(yva, rb._predict_full(lr_model, Xva))
            gb_model = rb._gbm_fit(Xtr, ytr, seed)
            thr_gb = rb.best_threshold(yva, rb._predict_full(gb_model, Xva))

            if single:
                gs_model, thr_gs = fit_graphsage_real(g, X_real, tr_idx, va_idx, seed)
                gs_scores = _graphsage_scores(
                    gs_model, torch.tensor(Xc, dtype=torch.float32),
                    build_adjacency(cluster["edges"], cluster["n"]))
            else:
                # Train on the pooled small graphs; threshold on the val graphs.
                Xpool = np.vstack([stack(graphs[i]) for i in tr_g])
                torch.manual_seed(seed)
                gs_model = GraphSAGE(in_dim=Xpool.shape[1], hidden=HIDDEN, dropout=0.3)
                opt = torch.optim.Adam(gs_model.parameters(), lr=0.01, weight_decay=1e-4)
                lossfn = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(3.0))
                batches = [(torch.tensor(stack(graphs[i]), dtype=torch.float32),
                            build_adjacency(graphs[i]["edges"], graphs[i]["n"]),
                            graphs[i]["y"].float()) for i in tr_g]
                for _ in range(EPOCHS):
                    gs_model.train(); opt.zero_grad()
                    tot = sum(lossfn(gs_model(x, a), y) for x, a, y in batches)
                    (tot / len(batches)).backward(); opt.step()
                gs_model.eval()
                with torch.no_grad():
                    pv = np.concatenate([
                        torch.sigmoid(gs_model(torch.tensor(stack(graphs[i]), dtype=torch.float32),
                                               build_adjacency(graphs[i]["edges"], graphs[i]["n"]))).numpy()
                        for i in va_g])
                thr_gs = rb.best_threshold(yva, pv)
                gs_scores = _graphsage_scores(
                    gs_model, torch.tensor(Xc, dtype=torch.float32),
                    build_adjacency(cluster["edges"], cluster["n"]))

            rule = rb.rule_scores(cluster["edges"], cluster["n"])

            scored = {
                "logistic_regression": (rb._predict_full(lr_model, Xc), thr_lr),
                "gradient_boosting": (rb._predict_full(gb_model, Xc), thr_gb),
                "graphsage": (gs_scores, thr_gs),
                "rule_only": (rule, 0.5),
            }
            row: Dict[str, Any] = {}
            for m, (s, t) in scored.items():
                flagged = int((np.asarray(s) >= t).sum())
                row[m] = {"flagged": flagged, "n": cluster["n"],
                          "flag_rate": flagged / cluster["n"],
                          "threshold": float(t)}
            per_seed.append(row)

        agg: Dict[str, Any] = {}
        for m in MODELS:
            rates = np.array([r[m]["flag_rate"] for r in per_seed])
            agg[m] = {"mean_flag_rate": float(rates.mean()),
                      "max_flag_rate": float(rates.max()),
                      "mean_flagged": float(np.mean([r[m]["flagged"] for r in per_seed])),
                      "cluster_size": cluster_size}
        out["shapes"][shape] = {"per_seed": per_seed, "aggregate": agg}
    return out


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", default="synthetic", choices=list(rb.DATASETS))
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    p.add_argument("--cluster-size", type=int, default=30)
    p.add_argument("--k", type=int, nargs="+", default=[50, 100])
    p.add_argument("--amlworld-path", default=os.environ.get("AMLWORLD_PATH"))
    p.add_argument("--limit-rows", type=int, default=None)
    p.add_argument("--out-dir", default="/tmp/benchmark_out")
    args = p.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    rb._PR_SEED = -1
    res = run_fp_stress(args.dataset, args.seeds, args.cluster_size, args.k,
                        amlworld_path=args.amlworld_path, limit_rows=args.limit_rows)
    path = os.path.join(args.out_dir, f"fp_stress_{args.dataset}.json")
    with open(path, "w") as fh:
        json.dump(res, fh, indent=2)
    print(f"[fp-stress] wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
