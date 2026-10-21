"""Seeded AMLSim-STYLE dataset generator (self-contained, reproducible).

IMPORTANT: this is NOT IBM's AMLSim and NOT the IBM AMLworld dataset. It is a
small generator we wrote that emits a CSV in the *published AMLworld header
format*, so the same loader (``amlworld_loader.py``) and the same benchmark
harness can run over both:

  * "self-generated synthetic (AMLSim-style)" — what this module produces
  * "IBM AMLworld"                            — the real file the user downloads

Keeping the two separate in docs/benchmarks.md is deliberate; generator results
never claim to validate real-world performance.

## What it models

A virtual world of bank accounts. Most transact normally; a few are planted
laundering rings:

  * **cycle ring**   — a closed loop of accounts passing funds around
  * **fan-in/out**   — many accounts pay one collector, which pays one exit

Transactions carry the native ``Is Laundering`` edge label, exactly as the real
dataset labels *transactions*, not accounts. The node-level label is derived by
the loader (participates in >= 1 laundering transaction).

## Determinism

Fully seeded. ``generate_dataset(seed)`` returns identical bytes for a given
seed, which is what lets the benchmark split be reproducible.

## Size ceiling (deliberate)

The default is a few thousand accounts, NOT the millions of transactions in the
real HI-Small file. The benchmark's cycle detector enumerates every simple cycle
of length 3–8 exactly (``nx.simple_cycles``) and computes exact betweenness;
both are exact-only, and both become intractable at HI-Small density. Scaling
the generator up would force approximating those two ops, which would silently
change what the reported rule/feature *means*. We keep the dataset at a size
where every operation in the harness is exact, and say so, rather than ship a
"scaled" number produced by a different algorithm than the one documented.

For the real dataset, cap the read with ``--limit-rows`` and the same exactness
holds on that prefix; the full HI-Small run is a separate, longer job.

## Identity

Accounts are ``(bank, account)`` pairs, matching the loader's identity rule.
"""

from __future__ import annotations

import csv
import io
import random
from typing import Any, Dict, List, Optional, Tuple

# The published header, including the duplicate "Account" column. pandas would
# rename the second to "Account.1"; we emit that directly so the file matches.
AMLWORLD_HEADER = [
    "Timestamp", "From Bank", "Account", "To Bank", "Account.1",
    "Amount Received", "Receiving Currency", "Amount Paid",
    "Payment Currency", "Payment Format", "Is Laundering",
]

PAYMENT_FORMATS = ["Reinvestment", "ACH", "Wire", "Cheque", "Credit Card", "Cash"]
CURRENCIES = ["US Dollar", "Euro", "Yuan", "Rupee", "Pound"]


def _fmt_ts(rng: random.Random, day: int) -> str:
    return f"2022/09/{day:02d} {rng.randrange(24):02d}:{rng.randrange(60):02d}"


def generate_dataset(
    seed: int,
    n_accounts: int = 4_000,
    n_rings: int = 8,
    ring_min: int = 4,
    ring_max: int = 8,
    fan_in: int = 10,
    background_edges: int = 10_000,
    n_banks: int = 20,
) -> Dict[str, Any]:
    """Emit one AMLSim-style dataset as CSV text + the derived graph.

    Returns::

        {
          "csv": str,                 # full CSV text (header + rows)
          "rows": [...],              # list of row lists
          "edge_labels": {(s,d):0/1}, # native transaction label per account pair
          "laundering_edges": [...],
          "account_keys": [...],      # "BANK:ACCOUNT"
          "seed": int,
        }
    """
    rng = random.Random(seed)

    accounts: List[Tuple[str, str]] = []          # (bank, account)
    keys: List[str] = []
    seen = set()

    def new_account() -> int:
        while True:
            bank = str(rng.randrange(1, n_banks + 1))
            acct = f"{rng.randrange(10**6, 10**7)}{rng.choice('ABCDEFG')}"
            key = f"{bank}:{acct}"
            if key not in seen:
                seen.add(key)
                accounts.append((bank, acct))
                keys.append(key)
                return len(accounts) - 1

    for _ in range(n_accounts):
        new_account()

    # --- Planted rings -----------------------------------------------------
    laundering_pairs: List[Tuple[int, int]] = []

    for _ in range(n_rings):
        size = rng.randint(ring_min, ring_max)
        members = [new_account() for _ in range(size)]
        for i in range(size):
            laundering_pairs.append((members[i], members[(i + 1) % size]))

    # Fan-in / fan-out: many -> collector -> exit
    for _ in range(n_rings):
        collectors = [rng.randrange(n_accounts) for _ in range(max(1, fan_in))]
        hub = new_account()
        exit_acct = new_account()
        for c in collectors:
            laundering_pairs.append((c, hub))
        laundering_pairs.append((hub, exit_acct))

    # --- Background (normal) traffic ---------------------------------------
    bg_pairs: List[Tuple[int, int]] = []
    for _ in range(background_edges):
        a = rng.randrange(n_accounts)
        b = rng.randrange(n_accounts)
        if a != b:
            bg_pairs.append((a, b))

    launder_set = set(laundering_pairs)
    rows: List[List[str]] = []
    edge_labels: Dict[Tuple[int, int], int] = {}

    def emit(src: int, dst: int, label: int, day: int) -> None:
        sb, sa = accounts[src]
        db, da = accounts[dst]
        amt = rng.randrange(50, 500_000) / 100.0
        amt_paid = amt * (1 + rng.uniform(-0.02, 0.02))
        cur = rng.choice(CURRENCIES)
        rows.append([
            _fmt_ts(rng, day), sb, sa, db, da, f"{amt:.2f}", cur,
            f"{amt_paid:.2f}", cur, rng.choice(PAYMENT_FORMATS), str(label),
        ])
        edge_labels[(src, dst)] = max(edge_labels.get((src, dst), 0), label)

    for src, dst in laundering_pairs:
        emit(src, dst, 1, rng.randint(1, 28))
    for src, dst in bg_pairs:
        if (src, dst) in launder_set:
            continue
        # A background pair may coincidentally be a laundering pair; the native
        # label stays 1 if any transaction on that pair is laundering.
        emit(src, dst, edge_labels.get((src, dst), 0), rng.randint(1, 28))

    rows.sort(key=lambda r: r[0])

    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(AMLWORLD_HEADER)
    w.writerows(rows)

    return {
        "csv": buf.getvalue(),
        "rows": rows,
        "edge_labels": edge_labels,
        "laundering_edges": sorted({p for p in laundering_pairs}),
        "account_keys": keys,
        "seed": seed,
    }


def write_dataset(path: str, seed: int, **kwargs) -> Dict[str, Any]:
    """Generate and write to ``path`` (CSV). Returns the dataset dict."""
    ds = generate_dataset(seed=seed, **kwargs)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(ds["csv"])
    return ds


def default_dataset_path(seed: int) -> str:
    import os
    return os.path.join("/tmp/amlsim_style", f"amlsim_style_seed{seed}.csv")
