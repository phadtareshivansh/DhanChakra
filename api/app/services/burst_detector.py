"""Burst detection for invoice activity (B2).

Uses z-score over rolling windows per (seller, buyer) pair to flag sudden
high-volume bursts relative to the pair's history. Deterministic and
testable with no external dependencies.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple


def _to_date(d: Any) -> Optional[date]:
    if d is None:
        return None
    if isinstance(d, date) and not hasattr(d, "hour"):
        return d
    try:
        from datetime import datetime

        if isinstance(d, datetime):
            return d.date()
    except Exception:
        pass
    try:
        s = str(d)
        if "T" in s:
            s = s.split("T")[0]
        return date.fromisoformat(s[:10])
    except Exception:
        return None


def detect_bursts(
    invoices: List[Dict[str, Any]],
    window_days: int = 7,
    z_threshold: float = 2.0,
    min_txns: int = 3,
) -> List[Dict[str, Any]]:
    """Return burst windows per (seller, buyer) pair.

    For each pair, aggregate invoice amounts by week/window and compute a
    z-score against the pair's own mean/std over historical windows.
    Windows with z >= threshold and >= min_txns are flagged as bursts.
    """
    if not invoices or window_days <= 0:
        return []

    # Group by pair
    by_pair: Dict[Tuple[str, str], List[Tuple[date, float]]] = defaultdict(list)
    for inv in invoices:
        seller = inv.get("seller_cin") or inv.get("from_cin") or inv.get("seller_id")
        buyer = inv.get("buyer_cin") or inv.get("to_cin") or inv.get("buyer_id")
        if not seller or not buyer:
            continue
        d = _to_date(inv.get("date") or inv.get("invoice_date"))
        if not d:
            continue
        try:
            amt = float(inv.get("amount") or 0)
        except Exception:
            amt = 0.0
        by_pair[(str(seller), str(buyer))].append((d, amt))

    bursts: List[Dict[str, Any]] = []
    for (seller, buyer), items in by_pair.items():
        if len(items) < min_txns:
            continue
        # Bin into windows starting from first date
        items_sorted = sorted(items, key=lambda x: x[0])
        first = items_sorted[0][0]
        bins: Dict[int, Dict[str, Any]] = {}
        for d, amt in items_sorted:
            idx = (d - first).days // window_days
            if idx not in bins:
                bins[idx] = {"start": first + timedelta(days=idx * window_days),
                             "end": first + timedelta(days=(idx + 1) * window_days - 1),
                             "count": 0, "total": 0.0}
            bins[idx]["count"] += 1
            bins[idx]["total"] += amt

        if len(bins) < 2:
            continue
        # History = all windows except current; need >=1 history window
        bin_list = sorted(bins.items(), key=lambda x: x[0])
        for i, (idx, b) in enumerate(bin_list):
            history = [bin_list[j][1]["total"] for j in range(i) if j < i]
            if not history:
                continue
            mean_h = sum(history) / len(history)
            var = sum((x - mean_h) ** 2 for x in history) / len(history)
            std = var ** 0.5
            if std <= 1e-9:
                continue
            z = (b["total"] - mean_h) / std
            if z >= z_threshold and b["count"] >= min_txns:
                bursts.append({
                    "seller_cin": seller,
                    "buyer_cin": buyer,
                    "start_date": b["start"].isoformat(),
                    "end_date": b["end"].isoformat(),
                    "window_days": window_days,
                    "count": b["count"],
                    "total_amount": round(b["total"], 2),
                    "z_score": round(z, 3),
                    "mean_history": round(mean_h, 2),
                })

    bursts.sort(key=lambda x: x["z_score"], reverse=True)
    return bursts
