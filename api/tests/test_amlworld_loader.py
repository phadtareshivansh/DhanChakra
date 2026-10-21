"""Guards for the AMLworld loader (api/benchmarks/amlworld_loader.py).

These run against a small HAND-WRITTEN fixture that mimics the published header
format (including the duplicate ``Account`` column). The real CSV is never
committed; see api/tests/fixtures/README.md.

Run: docker compose exec api pytest tests/test_amlworld_loader.py -q
"""

import os
import sys

import pytest

sys.path.insert(0, "/benchmarks")

import amlworld_loader as aw  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(HERE, "fixtures", "amlworld_hi_small_sample.csv")


def test_fixture_exists_and_has_duplicate_account_header():
    header = aw.read_header(FIXTURE)
    # The published quirk: two account-ish columns.
    assert "Account" in header and "Account.1" in header
    assert header[:4] == ["Timestamp", "From Bank", "Account", "To Bank"]
    assert header[-1] == "Is Laundering"


def test_resolves_both_dialects_required_fields():
    header = aw.read_header(FIXTURE)
    dialect, mapping, _ = aw._resolve_header(header)
    assert dialect == "amlworld"
    for field in ("timestamp", "from_bank", "from_account", "to_bank",
                  "to_account", "amount_received", "is_laundering"):
        assert field in mapping, f"unresolved {field}"


def test_account_columns_are_positional_not_collapsed():
    header = aw.read_header(FIXTURE)
    _, mapping, _ = aw._resolve_header(header)
    # sender = column index 2, receiver = column index 4 (past From Bank/To Bank)
    assert mapping["from_account"] == 2
    assert mapping["to_account"] == 4
    assert mapping["from_account"] != mapping["to_account"]


def test_header_matched_case_and_whitespace_insensitively():
    weird = ["  timestamp ", "FROM BANK", "account", "To  Bank", "ACCOUNT.1",
             "Amount  Received", "receiving currency", "amount paid",
             "payment currency", "payment format", " is laundering"]
    dialect, mapping, _ = aw._resolve_header(weird)
    assert dialect == "amlworld"
    assert mapping["from_account"] == 2 and mapping["to_account"] == 4
    assert mapping["is_laundering"] == 10


def test_malformed_header_fails_fast_with_both_headers():
    bad = ["a", "b", "c", "d"]
    with pytest.raises(aw.AmlworldSchemaError) as exc:
        aw._resolve_header(bad)
    msg = str(exc.value)
    assert "header found" in msg and "header expected" in msg
    assert "a, b, c, d" in msg          # what we actually found
    assert "Timestamp" in msg           # what we expected


def test_native_amlsim_dialect_also_resolves():
    native = ["tran_id", "orig_acct", "bene_acct", "tx_type", "base_amt",
              "tran_timestamp", "is_sar", "alert_id"]
    dialect, mapping, _ = aw._resolve_header(native)
    assert dialect == "amlsim"
    assert mapping["from_account"] == 1 and mapping["to_account"] == 2
    assert mapping["is_laundering"] == 6


def test_load_amlworld_report_and_identity():
    g = aw.load_amlworld(FIXTURE, verbose=False)
    r = g["report"]
    assert r["dialect"] == "amlworld"
    assert r["rows_read"] == 12
    assert r["rows_skipped_missing_id"] == 0

    # (bank, account) identity: 8000A1 appears only under bank 100 in this
    # fixture, but the key must be the pair either way.
    assert "100:8000A1" in g["index"]

    # Node label is DERIVED from the native edge label.
    assert r["laundering_transactions"] == 2
    assert r["derived_positive_accounts"] == 3
    positives = {g["accounts"][i] for i, v in enumerate(g["y"]) if v == 1}
    # The fixture marks two laundering edges: 300:7000C1 -> 100:8000A1 and
    # 600:4000F1 -> 100:8000A1. So their endpoints are positive.
    assert positives == {"300:7000C1", "100:8000A1", "600:4000F1"}


def test_same_account_string_under_two_banks_is_two_nodes(tmp_path):
    header = ["Timestamp", "From Bank", "Account", "To Bank", "Account.1",
              "Amount Received", "Receiving Currency", "Amount Paid",
              "Payment Currency", "Payment Format", "Is Laundering"]
    rows = [
        ["2022/09/01 00:00", "111", "ACCT9", "222", "ACCT8", "10", "USD", "10", "USD", "ACH", "0"],
        ["2022/09/01 01:00", "222", "ACCT9", "111", "ACCT8", "10", "USD", "10", "USD", "ACH", "0"],
    ]
    p = tmp_path / "dup.csv"
    p.write_text(aw.to_csv_string(rows, header))
    g = aw.load_amlworld(str(p), verbose=False)
    assert "111:ACCT9" in g["index"]
    assert "222:ACCT9" in g["index"]
    assert "111:ACCT9" != "222:ACCT9"
    # two distinct nodes despite the identical account string
    assert g["n"] == 4


def test_duplicate_edge_aggregates_any_laundering(tmp_path):
    header = ["Timestamp", "From Bank", "Account", "To Bank", "Account.1",
              "Amount Received", "Receiving Currency", "Amount Paid",
              "Payment Currency", "Payment Format", "Is Laundering"]
    rows = [
        ["2022/09/01 00:00", "1", "A", "2", "B", "10", "USD", "10", "USD", "ACH", "0"],
        ["2022/09/01 01:00", "1", "A", "2", "B", "10", "USD", "10", "USD", "ACH", "1"],
    ]
    p = tmp_path / "dup2.csv"
    p.write_text(aw.to_csv_string(rows, header))
    g = aw.load_amlworld(str(p), verbose=False)
    assert len(g["edges"]) == 1                 # deduplicated
    assert g["edge_labels"][g["edges"][0]] == 1  # any laundering wins


def test_missing_file_fails_with_a_clear_message(tmp_path):
    with pytest.raises(SystemExit) as exc:
        aw.load_amlworld(str(tmp_path / "nope.csv"), verbose=False)
    assert "not found" in str(exc.value)
    assert "docs/benchmarks.md" in str(exc.value)


def test_load_is_deterministic():
    a = aw.load_amlworld(FIXTURE, verbose=False)
    b = aw.load_amlworld(FIXTURE, verbose=False)
    assert a["accounts"] == b["accounts"]
    assert a["edges"] == b["edges"]
    assert a["y"] == b["y"]


def test_chunked_read_matches_single_chunk():
    """Streaming must not change the result."""
    big = aw.load_amlworld(FIXTURE, chunk_rows=100, verbose=False)
    small = aw.load_amlworld(FIXTURE, chunk_rows=2, verbose=False)
    assert big["accounts"] == small["accounts"]
    assert big["edges"] == small["edges"]
    assert big["y"] == small["y"]


def test_limit_rows_is_respected():
    g = aw.load_amlworld(FIXTURE, limit_rows=3, verbose=False)
    assert g["report"]["rows_read"] == 3
