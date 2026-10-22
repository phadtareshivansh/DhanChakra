#!/usr/bin/env python3
"""Export the torch GNN checkpoint to a torch-free .npz.

The production Render image does not install torch. It runs the same
GraphSAGE forward pass in numpy against the weights exported here, which
keeps the 512 MB free instance comfortable and the image small.

Usage (from a Python environment that has torch):
    python scripts/export_gnn_npz.py
    python scripts/export_gnn_npz.py api/models/gnn_risk_v1.pt api/models/gnn_risk_v1.npz

Inside the dev API container (the repo's scripts/ dir is mounted at /scripts):
    docker compose exec api python /scripts/export_gnn_npz.py
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch


def _default_src() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    for candidate in (
        Path("/app/models/gnn_risk_v1.pt"),
        repo_root / "api" / "models" / "gnn_risk_v1.pt",
        Path.cwd() / "api" / "models" / "gnn_risk_v1.pt",
    ):
        if candidate.exists():
            return str(candidate)
    return str(repo_root / "api" / "models" / "gnn_risk_v1.pt")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", nargs="?", default=_default_src())
    parser.add_argument("dst", nargs="?", default=None)
    args = parser.parse_args()

    src = Path(args.src)
    dst = Path(args.dst) if args.dst else src.with_suffix(".npz")
    checkpoint = torch.load(src, map_location="cpu", weights_only=True)
    state = checkpoint["model_state"]

    np.savez(
        dst,
        conv1_weight=state["conv1.weight"].numpy(),
        conv1_bias=state["conv1.bias"].numpy(),
        conv2_weight=state["conv2.weight"].numpy(),
        conv2_bias=state["conv2.bias"].numpy(),
        feature_cols=np.array(json.dumps(checkpoint["feature_cols"])),
        version=np.array(str(checkpoint.get("version", "unknown"))),
        trained_at=np.array(str(checkpoint.get("trained_at", ""))),
    )
    print(f"wrote {dst} ({dst.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
