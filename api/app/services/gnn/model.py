"""GraphSAGE-style model in plain PyTorch + training/metrics helpers.

Message passing is done with a row-normalized adjacency sparse matmul, so the
module works without torch-geometric/scatter wheels. Two SAGE conv layers with
mean aggregation, matching the plan (2-3 layers) for the small graphs here.
"""

import math
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F


class GraphSAGE(nn.Module):
    def __init__(self, in_dim: int, hidden: int = 16, dropout: float = 0.3):
        super().__init__()
        self.conv1 = nn.Linear(in_dim * 2, hidden)
        self.conv2 = nn.Linear(hidden * 2, 1)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor, a_norm: torch.Tensor) -> torch.Tensor:
        h = self._sage(x, a_norm, self.conv1)
        h = F.relu(h)
        h = self.dropout(h)
        h = self._sage(h, a_norm, self.conv2)
        return h.squeeze(-1)

    @staticmethod
    def _sage(x: torch.Tensor, a_norm: torch.Tensor, lin: nn.Linear) -> torch.Tensor:
        agg = a_norm @ x
        return lin(torch.cat([x, agg], dim=-1))


def build_adjacency(edges: List[Tuple[int, int]], n: int) -> torch.Tensor:
    """Row-normalized directed adjacency (self-loops included)."""
    a = torch.zeros(n, n)
    for src, dst in edges:
        if 0 <= src < n and 0 <= dst < n:
            a[src, dst] += 1.0
    a += torch.eye(n)
    row_sum = a.sum(dim=1, keepdim=True).clamp_min(1.0)
    return a / row_sum


def train_model(
    x: torch.Tensor,
    a_norm: torch.Tensor,
    labels: torch.Tensor,
    epochs: int = 200,
    lr: float = 0.01,
    weight_decay: float = 1e-4,
    seed: int = 42,
) -> Tuple[GraphSAGE, List[float]]:
    torch.manual_seed(seed)
    model = GraphSAGE(in_dim=x.shape[1])
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    losses = []
    for _ in range(epochs):
        model.train()
        opt.zero_grad()
        logits = model(x, a_norm)
        loss = F.binary_cross_entropy_with_logits(logits, labels.float())
        loss.backward()
        opt.step()
        losses.append(loss.item())
    return model, losses


def evaluate(
    scores: torch.Tensor, labels: torch.Tensor, k: Optional[int] = None
) -> Dict[str, float]:
    """F1 / AUC-PR / recall@k (TRD §9). Pure torch, no sklearn."""
    y = labels.float()
    p = torch.sigmoid(scores)
    preds = (p >= 0.5).float()

    tp = float((preds * y).sum())
    fp = float((preds * (1 - y)).sum())
    fn = float(((1 - preds) * y).sum())
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

    # AUC-PR: sort by descending score, trapezoid over cumulative recall
    order = torch.argsort(p, descending=True)
    y_sorted = y[order]
    pos_total = float(y_sorted.sum())
    if pos_total == 0 or len(y_sorted) == 0:
        auc_pr = 1.0 if pos_total == 0 else 0.0
    else:
        cum_tp = 0.0
        prev_r, prev_p = 0.0, 1.0
        auc_pr = 0.0
        for i, yi in enumerate(y_sorted.tolist(), start=1):
            cum_tp += yi
            r = cum_tp / pos_total
            p = cum_tp / i
            auc_pr += (r - prev_r) * (p + prev_p) / 2.0
            prev_r, prev_p = r, p

    k = k or max(1, int(pos_total))
    topk = y_sorted[:k]
    recall_at_k = float(topk.sum()) / pos_total if pos_total else 1.0

    return {"f1": round(f1, 4), "auc_pr": round(auc_pr, 4), "recall_at_k": round(recall_at_k, 4)}


def weighted_f1_loss(logits: torch.Tensor, labels: torch.Tensor, pos_weight: float = 3.0):
    """Class-imbalanced BCE (fraud is rare)."""
    return F.binary_cross_entropy_with_logits(logits, labels.float(), pos_weight=torch.tensor(pos_weight))