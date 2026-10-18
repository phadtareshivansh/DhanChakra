"""Phase 3 training CLI.

Steps:
1. Pretrain GraphSAGE on the synthetic AML-style benchmark (metrics per TRD §9).
2. Fine-tune on the live India-shaped graph using structural weak labels.
3. Persist checkpoint + metrics; register a model_versions row (schema §3).

Usage (inside the API container):
    python -m app.services.gnn.train [--epochs 200] [--no-finetune] [--no-register]
"""

import argparse
import json
import os
import sys
import uuid
from typing import Any, Dict, List

import torch

from ...config import settings
from . import features as feat
from .model import GraphSAGE, build_adjacency, evaluate, train_model, weighted_f1_loss
from .synthetic import generate_benchmark, split_benchmark

CHECKPOINT_DIR = settings.gnn_checkpoint_dir
CHECKPOINT_PATH = settings.gnn_checkpoint_file
METRICS_PATH = os.path.join(CHECKPOINT_DIR, settings.gnn_metrics_filename)


async def _extract_live(session) -> Dict[str, Any]:
    data = await feat.extract_graph(session)
    n = len(data["companies"])
    if n == 0:
        return None
    idx = {c["id"]: i for i, c in enumerate(data["companies"])}
    edges = [(idx[s], idx[d]) for s, d in data["edges"] if s in idx and d in idx]
    x = torch.tensor([c["_features"] for c in data["companies"]], dtype=torch.float32)
    a_norm = build_adjacency(edges, n)
    y = torch.tensor(feat.weak_labels(data["companies"]), dtype=torch.float32)
    return {"x": x, "a_norm": a_norm, "y": y, "companies": data["companies"]}


_pretrain_metrics: Dict[str, float] = {}


def _pretrain(args) -> GraphSAGE:
    print("[gnn] generating synthetic benchmark...")
    graphs = generate_benchmark(n_graphs=args.benchmark_graphs)
    train_g, test_g = split_benchmark(graphs, frac=0.8)

    torch.manual_seed(42)
    model = GraphSAGE(in_dim=graphs[0]["x"].shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=1e-4)
    losses = []
    for _ in range(args.epochs):
        model.train()
        for g in train_g:
            opt.zero_grad()
            logits = model(g["x"], g["a_norm"])
            loss = weighted_f1_loss(logits, g["y"])
            loss.backward()
            opt.step()
            losses.append(loss.item())

    model.eval()
    with torch.no_grad():
        all_scores, all_labels = [], []
        for g in test_g:
            all_scores.append(torch.sigmoid(model(g["x"], g["a_norm"])))
            all_labels.append(g["y"])
    metrics = evaluate(torch.cat(all_scores), torch.cat(all_labels))
    print(f"[gnn] benchmark eval: {metrics}")
    global _pretrain_metrics
    _pretrain_metrics = metrics
    return model


def _finetune(model: GraphSAGE, live: Dict[str, Any], epochs: int) -> None:
    x, a_norm, y = live["x"], live["a_norm"], live["y"]
    opt = torch.optim.Adam(model.parameters(), lr=0.005, weight_decay=1e-4)
    model.train()
    for _ in range(epochs):
        opt.zero_grad()
        loss = weighted_f1_loss(model(x, a_norm), y)
        loss.backward()
        opt.step()


async def run_pipeline(session, args) -> Dict[str, Any]:
    model = _pretrain(args)

    global _last_benchmark
    _last_benchmark = _pretrain_metrics
    live = await _extract_live(session)
    if live is not None and not args.no_finetune:
        print(f"[gnn] fine-tuning on live graph ({live['x'].shape[0]} companies)...")
        _finetune(model, live, args.finetune_epochs)
        model.eval()
        with torch.no_grad():
            scores = torch.sigmoid(model(live["x"], live["a_norm"]))
            live_metrics = evaluate(scores, live["y"])
        print(f"[gnn] live weak-label eval: {live_metrics}")
    else:
        live_metrics = {}

    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    torch.save(
        {
            "model_state": model.state_dict(),
            "feature_cols": feat.FEATURE_COLS,
            "version": "gnn_risk_v1",
            "trained_at": str(uuid.uuid4()),
        },
        CHECKPOINT_PATH,
    )
    metrics = {"benchmark": _last_benchmark, "live": live_metrics}
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"[gnn] checkpoint saved: {CHECKPOINT_PATH}")
    return {"checkpoint": CHECKPOINT_PATH, "metrics": metrics, "live_size": live["x"].shape[0] if live else 0}


_last_benchmark: Dict[str, float] = {}


async def register_version(db, summary: Dict[str, Any], version_tag: str = "gnn_risk_v1") -> None:
    """Insert into model_versions (Backend Schema §3). `db` is a SQLAlchemy
    async session (from app.deps.async_session_maker)."""
    from sqlalchemy import text

    async with db.begin():
        await db.execute(
            text("""
            UPDATE model_versions SET is_active = false WHERE is_active = true
            """)
        )
        await db.execute(
            text("""
            INSERT INTO model_versions (version_tag, trained_on, metrics, checkpoint_path, deployed_at, is_active)
            VALUES (:tag, :trained_on, :metrics, :path, now(), true)
            """),
            {
                "tag": version_tag,
                "trained_on": "synthetic_aml_benchmark + india_weak_labels",
                "metrics": json.dumps(summary.get("metrics", {})),
                "path": CHECKPOINT_PATH,
            },
        )


def _default_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=settings.gnn_default_epochs)
    p.add_argument("--finetune-epochs", type=int, default=settings.gnn_finetune_epochs)
    p.add_argument("--benchmark-graphs", type=int, default=settings.gnn_benchmark_graphs)
    p.add_argument("--no-finetune", action="store_true")
    p.add_argument("--no-register", action="store_true")
    return p.parse_args([])


def main(argv: List[str] = None) -> None:
    parser = argparse.ArgumentParser(description="Dhan-Chakra GNN trainer (Phase 3)")
    parser.add_argument("--epochs", type=int, default=settings.gnn_default_epochs)
    parser.add_argument("--finetune-epochs", type=int, default=settings.gnn_finetune_epochs)
    parser.add_argument("--benchmark-graphs", type=int, default=settings.gnn_benchmark_graphs)
    parser.add_argument("--no-finetune", action="store_true")
    parser.add_argument("--no-register", action="store_true")
    args = parser.parse_args(argv)

    import asyncio

    async def _main():
        from app.deps import get_neo4j_session

        global _last_benchmark
        async with get_neo4j_session() as session:
            summary = await run_pipeline(session, args)
            _last_benchmark = summary["metrics"]["benchmark"]
        if not args.no_register:
            from app.deps import async_session_maker

            async with async_session_maker() as db:
                await register_version(db, summary)
            print("[gnn] model version registered in Postgres")
        print("[gnn] done")

    asyncio.run(_main())


if __name__ == "__main__":
    main()