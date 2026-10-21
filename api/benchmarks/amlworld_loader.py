"""Loader for the real IBM / AMLworld transaction CSV (start with HI-Small).

This reads the *published* CSV — it does NOT trust a fixed schema. The header row
is validated on load, matched case-insensitively and whitespace-insensitively,
and a mismatch fails fast with both the header that was found and the one that
was expected. Nothing is silently misparsed.

## Two known dialects

The native ``AMLSim`` output (``scripts/convert_logs.py``, schema in
``paramFiles/*/schema.json``) uses:

    tran_id, orig_acct, bene_acct, tx_type, base_amt, tran_timestamp,
    is_sar, alert_id

The IBM Kaggle "HI-Small" file — the dataset page the docs point at — uses a
renamed schema, widely cited as:

    Timestamp, From Bank, Account, To Bank, Account.1, Amount Received,
    Receiving Currency, Amount Paid, Payment Currency, Payment Format,
    Is Laundering

Note the **duplicate ``Account`` header**: column 3 is the sender account and
column 4 is the receiver account. pandas disambiguates the second occurrence
(e.g. ``Account.1``), so this loader resolves the two account columns
**positionally** and works whether or not the duplicate is present.

We could not verify the Kaggle header row from the build environment, so both
dialects are supported and detection is by header, not by a hard-coded schema.

## Identity: (bank, account), not account alone

Account identity is the pair ``(bank, account)``, not the account string on its
own, because the same account string can legitimately appear under different
banks in this dataset. Edges are therefore keyed by that pair and reported as
``BANK:ACCOUNT``. The same rule applies on both sides (sender and receiver).
See the "Identity" section of docs/benchmarks.md.

## Labels

The dataset labels **transactions** (``Is Laundering``), not accounts. This
loader additionally derives a node label = "account participates in at least one
laundering transaction". That derivation is ours, not the dataset's, and it is
documented as such in docs/benchmarks.md — including its known weakness, that a
legitimate account which merely *receives* laundered funds is labelled positive.

The native edge label is preserved per edge so an edge-level metric can also be
reported (see ``load_amlworld(..., as_graph=True)["edge_labels"]``).

## Streaming

``iter_chunks`` / ``iter_rows`` read in bounded chunks, so a larger variant
(LI-Small / HI-Large / LI-Large) does not need to fit in memory at once. The
full loader materialises only the graph, never the raw table.
"""

from __future__ import annotations

import csv
import io
import os
import sys
from collections import Counter
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# Schema dialects
# --------------------------------------------------------------------------

# Canonical column names -> accepted aliases (all matched case/space-insensitively).
_FIELD_ALIASES: Dict[str, Sequence[str]] = {
    "timestamp": ("timestamp", "tran_timestamp", "datetime"),
    "from_bank": ("from bank", "from_bank", "orig_bank"),
    "from_account": ("account", "from_account", "orig_acct", "sender_account"),
    "to_bank": ("to bank", "to_bank", "bene_bank", "dest_bank"),
    "to_account": ("account.1", "to_account", "bene_acct", "receiver_account"),
    "amount_received": ("amount received", "amount_received", "base_amt", "amount"),
    "receiving_currency": ("receiving currency", "receiving_currency"),
    "amount_paid": ("amount paid", "amount_paid"),
    "payment_currency": ("payment currency", "payment_currency"),
    "payment_format": ("payment format", "payment_format", "tx_type"),
    "is_laundering": ("is laundering", "is_laundering", "is_sar"),
    "currency": ("currency",),
    "tx_id": ("tran_id", "transaction_id", "tx_id"),
}

# The two dialects we accept. Each lists the human-readable expected header
# (what we tell the user we wanted) and the fields that MUST resolve.
_DIALECTS: Dict[str, Dict[str, Any]] = {
    "amlworld": {
        "label": "IBM AMLworld (Kaggle HI-Small style)",
        "expected": [
            "Timestamp", "From Bank", "Account", "To Bank", "Account.1",
            "Amount Received", "Receiving Currency", "Amount Paid",
            "Payment Currency", "Payment Format", "Is Laundering",
        ],
        "required": [
            "timestamp", "from_bank", "from_account", "to_bank", "to_account",
            "amount_received", "is_laundering",
        ],
        "account_columns_positional": True,
    },
    "amlsim": {
        "label": "native AMLSim (convert_logs.py output)",
        "expected": [
            "tran_id", "orig_acct", "bene_acct", "tx_type", "base_amt",
            "tran_timestamp", "is_sar", "alert_id",
        ],
        "required": [
            "timestamp", "from_account", "to_account", "amount_received",
            "is_laundering",
        ],
        "account_columns_positional": False,
    },
}

DEFAULT_CHUNK_ROWS = 200_000


def _norm(name: str) -> str:
    """Case- and whitespace-insensitive column key."""
    return " ".join(str(name).strip().lower().replace("_", " ").split())


class AmlworldSchemaError(ValueError):
    """Raised when the CSV header matches no known dialect."""


def _resolve_header(header: Sequence[str]) -> Tuple[str, Dict[str, int], List[str]]:
    """Map canonical fields to column indices for a raw header row.

    Handles the duplicate ``Account`` column positionally: the first occurrence
    is the sender, the second the receiver. Returns
    ``(dialect_name, {field: index}, normalised_header)``.
    """
    raw = [str(h) for h in header]
    norm = [_norm(h) for h in raw]

    # Which dialect matches? Prefer one whose REQUIRED fields can all resolve;
    # among those, the one resolving the most. This avoids picking a dialect on
    # a partial overlap (e.g. the native AMLSim header shares only a couple of
    # aliases with the Kaggle schema).
    def resolvable(name: str, spec: Dict[str, Any]) -> int:
        return sum(
            1 for f in spec["required"]
            if any(_norm(a) in norm for a in _FIELD_ALIASES[f])
        )

    scored = [(resolvable(name, spec), name) for name, spec in _DIALECTS.items()]
    full = [(n, name) for n, name in scored if n == len(_DIALECTS[name]["required"])]
    if full:
        best = max(full)
    else:
        best = max(scored)
    dialect = best[1]
    spec = _DIALECTS[dialect]

    # Positional account handling: repeated normalised name -> first/second.
    account_norm_aliases = {_norm(a) for a in _FIELD_ALIASES["from_account"]}
    account_positions = [i for i, h in enumerate(norm) if h in account_norm_aliases]

    mapping: Dict[str, int] = {}
    for field, aliases in _FIELD_ALIASES.items():
        want = {_norm(a) for a in aliases}
        hits = [i for i, h in enumerate(norm) if h in want]
        if not hits:
            continue
        if field == "from_account":
            mapping[field] = account_positions[0]
        elif field == "to_account":
            # Prefer the second "account"-ish column if the duplicate is present;
            # otherwise fall back to a distinct alias (e.g. bene_acct).
            distinct = [i for i in hits if _norm(raw[i]) not in account_norm_aliases]
            if len(account_positions) >= 2 and field not in mapping:
                mapping[field] = account_positions[1]
            elif distinct:
                mapping[field] = distinct[0]
            elif len(hits) >= 2:
                mapping[field] = hits[1]
        else:
            mapping[field] = hits[0]

    # If the explicit alias for to_account lost to "from_account", disambiguate
    # by position when two account-ish columns exist.
    if mapping.get("to_account") == mapping.get("from_account"):
        if len(account_positions) >= 2:
            mapping["to_account"] = account_positions[1]
        else:
            mapping.pop("to_account", None)
    if mapping.get("from_account") == mapping.get("to_account"):
        mapping.pop("to_account", None)

    missing = [f for f in spec["required"] if f not in mapping]
    if missing:
        expected = ", ".join(spec["expected"])
        found = ", ".join(raw)
        raise AmlworldSchemaError(
            "AMLworld loader: could not resolve required column(s) "
            f"{missing} in the {dialect} dialect ({spec['label']}).\n"
            f"  header found:    {found}\n"
            f"  header expected: {expected}\n"
            "Refusing to misparse. If this is a different variant, add its "
            "aliases to _FIELD_ALIASES (case/whitespace-insensitive)."
        )
    return dialect, mapping, norm


def read_header(path: str, delimiter: str = ",") -> List[str]:
    """Return the raw header row, decoded as UTF-8."""
    with open(path, "r", newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        return next(reader)


def iter_chunks(path: str, dialect_map: Dict[str, int],
                chunk_rows: int = DEFAULT_CHUNK_ROWS,
                delimiter: str = ",") -> Iterator[List[Dict[str, str]]]:
    """Yield lists of dicts, at most ``chunk_rows`` per list.

    Skips the header, tolerates short/ragged rows (they are passed through so the
    caller can classify and count them in the load report).
    """
    with open(path, "r", newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh, delimiter=delimiter)
        next(reader, None)  # header
        buf: List[Dict[str, str]] = []
        for row in reader:
            rec: Dict[str, str] = {}
            for field, idx in dialect_map.items():
                rec[field] = row[idx] if 0 <= idx < len(row) else ""
            rec["_ncols"] = str(len(row))
            buf.append(rec)
            if len(buf) >= chunk_rows:
                yield buf
                buf = []
        if buf:
            yield buf


def _account_key(bank: str, account: str) -> str:
    """(bank, account) identity, not the account string alone."""
    return f"{(bank or '').strip()}:{(account or '').strip()}"

def _parse_float(v: str) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _parse_label(v: str) -> int:
    s = str(v).strip().lower()
    if s in ("1", "1.0", "true", "yes", "y", "t"):
        return 1
    return 0


def load_amlworld(
    path: str,
    limit_rows: Optional[int] = None,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Load an AMLworld-format CSV into a graph dict.

    Returns::

        {
          "accounts": [key, ...],        # "BANK:ACCOUNT", stable order
          "index":    {key: node_id},
          "edges":    [(node_src, node_dst), ...],   # deduplicated
          "edge_labels": {edge_tuple: 0/1},          # native transaction label
          "y":        [0/1, ...],        # DERIVED node label (participates)
          "n":        int,
          "report":   {...},             # load report for sanity-checking
          "dialect":  str,
          "header":   [...],             # raw header as found
        }

    The node label is derived, not native: AMLworld labels transactions. See the
    module docstring.
    """
    if not os.path.exists(path):
        raise SystemExit(
            f"error: AMLworld file not found at {path}.\n"
            "Download it (see docs/benchmarks.md) and place it at "
            "data/amlworld/<file>.csv, or pass --amlworld-path."
        )

    header = read_header(path)
    dialect, mapping, _ = _resolve_header(header)

    accounts: List[str] = []
    index: Dict[str, int] = {}
    edge_set: Dict[Tuple[int, int], int] = {}
    edge_amount: Dict[Tuple[int, int], float] = {}
    laundering_transactions = 0
    rows_read = 0
    skipped_missing_id = 0
    skipped_no_laundering_col = 0
    skipped_short = 0
    seen_pairs: Dict[Tuple[str, str], int] = {}

    for chunk in iter_chunks(path, mapping, chunk_rows=chunk_rows):
        for rec in chunk:
            if limit_rows is not None and rows_read >= limit_rows:
                break
            rows_read += 1

            if "is_laundering" not in mapping:
                skipped_no_laundering_col += 1
                continue

            if int(rec.get("_ncols", "0")) < 2:
                skipped_short += 1
                continue

            bank_s, acct_s = (rec.get("from_bank", "") or "").strip(), (rec.get("from_account", "") or "").strip()
            bank_d, acct_d = (rec.get("to_bank", "") or "").strip(), (rec.get("to_account", "") or "").strip()
            if not acct_s or not acct_d:
                # an account string is required on both sides (the bank may be
                # blank in some variants, which still yields a usable key)
                skipped_missing_id += 1
                continue
            src_key = _account_key(bank_s, acct_s)
            dst_key = _account_key(bank_d, acct_d)

            lbl = _parse_label(rec.get("is_laundering", "0"))
            laundering_transactions += lbl

            if src_key not in index:
                index[src_key] = len(accounts)
                accounts.append(src_key)
            if dst_key not in index:
                index[dst_key] = len(accounts)
                accounts.append(dst_key)
            s, d = index[src_key], index[dst_key]

            # A repeated (src,dst) pair keeps the "any laundering" label.
            prev = edge_set.get((s, d))
            if prev is None:
                edge_set[(s, d)] = lbl
            else:
                edge_set[(s, d)] = 1 if (prev or lbl) else 0
            # Amounts: prefer "Amount Received", fall back to "Amount Paid"/"base_amt".
            amt = _parse_float(rec.get("amount_received", ""))
            if amt is None:
                amt = _parse_float(rec.get("amount_paid", ""))
            if amt is None:
                amt = _parse_float(rec.get("base_amt", ""))
            edge_amount[(s, d)] = edge_amount.get((s, d), 0.0) + float(amt or 0.0)
            seen_pairs[(src_key, dst_key)] = seen_pairs.get((src_key, dst_key), 0) + 1
        if limit_rows is not None and rows_read >= limit_rows:
            break

    edges = list(edge_set.keys())
    edge_labels = {e: edge_set[e] for e in edges}

    # DERIVED node label: participates in >=1 laundering transaction.
    y = [0] * len(accounts)
    for (s, d), lbl in edge_set.items():
        if lbl:
            y[s] = 1
            y[d] = 1
    positives = sum(y)

    report = {
        "path": path,
        "dialect": dialect,
        "header_found": header,
        "rows_read": rows_read,
        "rows_skipped_missing_id": skipped_missing_id,
        "rows_skipped_short": skipped_short,
        "accounts_created": len(accounts),
        "edges": len(edges),
        "laundering_transactions": laundering_transactions,
        "derived_positive_accounts": positives,
        "positive_rate_nodes": (positives / len(accounts)) if accounts else 0.0,
        "positive_rate_edges": (sum(edge_labels.values()) / len(edges)) if edges else 0.0,
        "note": (
            "node label is DERIVED (participates in >=1 laundering transaction); "
            "the dataset labels transactions, not accounts"
        ),
    }

    if verbose:
        print_load_report(report)

    return {
        "accounts": accounts,
        "index": index,
        "edges": edges,
        "edge_labels": edge_labels,
        "edge_amounts": [edge_amount.get(e, 0.0) for e in edges],
        "y": y,
        "n": len(accounts),
        "report": report,
        "dialect": dialect,
        "header": header,
    }


def print_load_report(report: Dict[str, Any]) -> None:
    """Short load report so the numbers can be checked against the dataset page."""
    out = sys.stdout
    print("[amlworld] load report", file=out)
    print(f"    file                      : {report['path']}", file=out)
    print(f"    dialect                   : {report['dialect']}", file=out)
    print(f"    rows read                 : {report['rows_read']}", file=out)
    print(f"    rows skipped (missing id) : {report['rows_skipped_missing_id']}", file=out)
    print(f"    rows skipped (short/ragged): {report['rows_skipped_short']}", file=out)
    print(f"    accounts created          : {report['accounts_created']}", file=out)
    print(f"    edges (unique pairs)      : {report['edges']}", file=out)
    print(f"    laundering transactions   : {report['laundering_transactions']}", file=out)
    print(f"    derived positive accounts : {report['derived_positive_accounts']} "
          f"({report['positive_rate_nodes']:.4%} of accounts)", file=out)


# --------------------------------------------------------------------------
# Self-generated AMLSim-style fixture/data (see amlsim_data.py for the real one)
# --------------------------------------------------------------------------

def to_csv_string(rows: Sequence[Sequence[Any]], header: Sequence[str]) -> str:
    """Tiny helper for tests: build a CSV string with an exact header."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    return buf.getvalue()
