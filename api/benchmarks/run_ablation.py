"""A2 item 3 — feature-group ablation for GraphSAGE (and the tabular models).

Retrains the same models with one feature group removed at a time and reports the
metric drop relative to the full headline view. Run on either dataset:

    python /benchmarks/run_ablation.py --dataset synthetic
    python /benchmarks/run_ablation.py --dataset amlsim
    python /benchmarks/run_ablation.py --dataset amlworld --amlworld-path /data/...

Groups (per the task list):

  * ``cycle``       — the recomputed cycle feature (headline excludes it anyway)
  * ``centrality``  — pagerank + betweenness
  * ``structural``  — clustering + reciprocity + shared_neighbors
  * ``attributes``  — degrees + the value/attribute column(s)
  * ``community``   — community-style share, when the feature set has one
  * ``shared_director`` / ``shared_address`` — reported as ABSENT when no dataset
    supplies them

The shared-director group is expected to be empty: neither the product generator
nor the AML datasets carry director/address data. It is reported as absent rather
than silently skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

for candidate in ("/app", "/benchmarks"):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

import numpy as np  # noqa: E402

import run_benchmark as rb  # noqa: E402

MODELS = ("logistic_regression", "gradient_boosting", "graphsage")

GROUPS: Dict[str, Sequence[str]] = {
    "cycle": ("recomputed_cycle_member",),
    "centrality": ("pagerank", "betweenness"),
    "structural": ("clustering", "reciprocity", "shared_neighbors"),
    "attributes": ("in_degree", "out_degree", "total_degree", "puc_log",
                   "in_amount", "out_amount", "amount_imbalance"),
    "community": ("community_share",),
}
ABSENT_GROUPS = {
    "shared_director": "no dataset here supplies director data",
    "shared_address": "no dataset here supplies address data",
}


def base_columns(dataset_graph: Dict[str, Any]) -> List[str]:
    return rb.AML_FEATURE_COLS if dataset_graph.get("x") is None \
        else rb.EDGE_FEATURE_COLS


_MATRIX_CACHE: Dict[int, Tuple[np.ndarray, List[str]]] = {}


def build_matrix(graph: Dict[str, Any], cols: Sequence[str],
                 all_cols: Sequence[str]) -> np.ndarray:
    """Feature matrix for ``graph`` restricted to ``cols`` (order of all_cols).

    The full (structural + value + cycle) matrix is computed once per graph and
    cached, then subset per variant. The base features and the exact 3–8 hop
    cycle column are both expensive, so recomputing them for every ablation
    variant would dominate the run.
    """
    key = id(graph)
    cached = _MATRIX_CACHE.get(key)
    if cached is None:
        aml = graph.get("x") is None
        base = (rb.build_aml_features(graph["edges"], graph["n"],
                                      amounts=graph.get("edge_amounts"))
                if aml else rb.build_features(graph["edges"], graph["n"]))
        extra = rb.recompute_cycle_members(graph["edges"], graph["n"]).reshape(-1, 1)
        full_cols = list(all_cols) + ["recomputed_cycle_member"]
        full = np.hstack([base, extra])
        cached = (full, full_cols)
        _MATRIX_CACHE[key] = cached
    full, full_cols = cached
    idx = [full_cols.index(c) for c in cols]
    return full[:, idx]


def run_ablation(dataset: str, seeds: Sequence[int], n_graphs: int,
                 k_values: Sequence[int], amlworld_path: Optional[str] = None,
                 limit_rows: Optional[int] = None) -> Dict[str, Any]:
    per_seed: Dict[str, List[Dict[str, Any]]] = {}
    available: Dict[str, List[str]] = {}
    first_cols: List[str] = []

    for seed in seeds:
        print(f"[ablation] seed {seed} ...", flush=True)
        _MATRIX_CACHE.clear()  # id() reuse hazard across seeds
        graphs = rb.build_dataset({"name": dataset}, seed, n_graphs,
                                  amlworld_path=amlworld_path, limit_rows=limit_rows)
        tr, va, te = rb.dataset_split(graphs, seed=seed)
        single = len(graphs) == 1
        all_cols = base_columns(graphs[0])
        first_cols = all_cols

        available = {g: [c for c in cols if c in all_cols] for g, cols in GROUPS.items()}

        def stack(cols: Sequence[str]) -> np.ndarray:
            if single:
                return build_matrix(graphs[0], cols, all_cols)
            return np.vstack([build_matrix(graphs[i], cols, all_cols) for i in range(len(graphs))])

        def labels(idx):
            if single:
                return graphs[0]["y"].numpy().astype(int)[idx]
            return np.concatenate([graphs[i]["y"].numpy() for i in idx]).astype(int)

        yte, ytr, yva = labels(te), labels(tr), labels(va)
        k_records = {}
        for k_req in k_values:
            k_use = min(k_req, len(yte))
            k_records[k_req] = {"k_used": int(k_use), "clamped": bool(k_use < k_req)}

        variants: Dict[str, List[str]] = {"full": list(all_cols)}
        for g, cols in GROUPS.items():
            present = [c for c in cols if c in all_cols]
            if present:
                variants[f"minus_{g}"] = [c for c in all_cols if c not in set(present)]
        variants["plus_cycle"] = list(all_cols) + ["recomputed_cycle_member"]

        for name, cols in variants.items():
            X = stack(cols)
            Xtr, Xva, Xte = X[tr], X[va], X[te]
            row: Dict[str, Any] = {"columns": list(cols)}

            _, pt_lr, thr_lr, _ = rb.fit_predict_lr(Xtr, ytr, Xva, yva, Xte, seed)
            _, pt_gb, thr_gb, _ = rb.fit_predict_gbm(Xtr, ytr, Xva, yva, Xte, seed)
            if single:
                _, pt_gs, thr_gs, _ = rb.fit_predict_graphsage_single(
                    graphs[0], tr, va, te, lambda c=cols: stack(c), seed)
            else:
                def view_stack(i, _c=cols):
                    g = graphs[i]
                    return build_matrix(g, _c, all_cols)
                _, pt_gs, thr_gs, _ = rb.fit_predict_graphsage(graphs, tr, va, te, view_stack, seed)

            for mname, (pt, thr) in (("logistic_regression", (pt_lr, thr_lr)),
                                     ("gradient_boosting", (pt_gb, thr_gb)),
                                     ("graphsage", (pt_gs, thr_gs))):
                row[mname] = rb.metrics_at(yte, pt, thr, k_values, k_records)
            per_seed.setdefault(name, []).append(row)

    out: Dict[str, Any] = {
        "dataset": dataset, "seeds": list(seeds), "n_graphs": n_graphs,
        "k": list(k_values), "available_groups": available,
        "absent_groups": ABSENT_GROUPS, "results": {},
    }
    for name, rows in per_seed.items():
        out["results"][name] = {
            "columns": rows[0]["columns"],
            "models": {m: rb.aggregate([r[m] for r in rows]) for m in MODELS},
        }

    fullagg = out["results"]["full"]["models"]
    for name, rec in out["results"].items():
        if name == "full":
            continue
        rec["delta_vs_full"] = {
            m: {metric: _delta(fullagg[m][metric]["mean"],
                               rec["models"][m][metric]["mean"])
                for metric in ("auc_pr", "precision@50", "recall@50")}
            for m in MODELS
        }
    return out


def _delta(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return None if (a is None or b is None) else b - a


def main(argv: List[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", default="synthetic", choices=list(rb.DATASETS))
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    p.add_argument("--graphs", type=int, default=60)
    p.add_argument("--k", type=int, nargs="+", default=[50, 100])
    p.add_argument("--amlworld-path", default=os.environ.get("AMLWORLD_PATH"))
    p.add_argument("--limit-rows", type=int, default=None)
    p.add_argument("--out-dir", default="/tmp/benchmark_out")
    args = p.parse_args(argv)

    os.makedirs(args.out_dir, exist_ok=True)
    rb._PR_SEED = -1  # no PR capture during ablation
    res = run_ablation(args.dataset, args.seeds, args.graphs, args.k,
                       amlworld_path=args.amlworld_path, limit_rows=args.limit_rows)
    path = os.path.join(args.out_dir, f"ablation_{args.dataset}.json")
    with open(path, "w") as fh:
        json.dump(res, fh, indent=2)
    print(f"[ablation] wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
