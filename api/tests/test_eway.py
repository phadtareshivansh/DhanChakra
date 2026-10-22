"""Tests for the e-Way Bill mismatch signal (TASK B1).

The signal is "this high-value invoice has no matching e-Way Bill movement
record" -- not "this invoice has no reference string". These tests cover both
halves of that: the rule itself (`app.services.eway_service`) and the places
that consume it (the GNN feature extractor, the heuristic score, the explain
endpoint and the network response the UI badges).

Unit tests need no database. The live tests run against the running stack.

Usage: docker compose exec api pytest tests -q
"""

import asyncio

import pytest

from app.config import settings
from app.services import eway_service as eway
from app.services import graph_service
from app.services.gnn import features as gnn_features


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# --- The rule (pure) --------------------------------------------------------


def test_classify_missing_reference():
    assert eway.classify_mismatch(900000, None) == eway.MISMATCH_NO_REF
    assert eway.classify_mismatch(900000, "") == eway.MISMATCH_NO_REF
    assert eway.classify_mismatch(900000, "   ") == eway.MISMATCH_NO_REF


def test_classify_reference_without_movement_record():
    assert eway.classify_mismatch(900000, "EWB-X1", None) == eway.MISMATCH_NO_MOVEMENT


def test_classify_amount_mismatch():
    # 800k invoice, 620k movement record -> 180k apart, far past tolerance.
    assert eway.classify_mismatch(800000, "EWB-X2", 620000) == eway.MISMATCH_AMOUNT


def test_classify_exact_match_is_clean():
    assert eway.classify_mismatch(900000, "EWB-X3", 900000) is None


def test_classify_within_tolerance_is_clean():
    # 1% apart, tolerance is 5% of the invoice -> clean.
    assert eway.classify_mismatch(100000, "EWB-X4", 99000) is None


def test_amount_tolerance_has_an_absolute_floor():
    # 1,500 invoice, 1,000 movement record: 500 apart is past the 5% share
    # (75) but the absolute floor (1,000) is what applies, so 500 is clean.
    assert eway.tolerance_for(1500) == settings.eway_amount_tolerance_min
    assert eway.classify_mismatch(1500, "EWB-X5", 1000) is None
    # 1,500 vs 400 is 1,100 apart -> past the floor -> a real mismatch.
    assert eway.classify_mismatch(1500, "EWB-X5", 400) == eway.MISMATCH_AMOUNT


def test_in_coverage_requires_a_loaded_feed():
    # No feed at all -> covers nothing -> "no movement record" cannot be
    # asserted, so an invoice must not be flagged on that ground.
    assert eway.in_coverage("2024-03-01", None, None) is False


def test_in_coverage_window():
    assert eway.in_coverage("2024-03-01", "2024-01-01", "2024-06-30") is True
    assert eway.in_coverage("2024-01-01", "2024-01-01", "2024-06-30") is True
    assert eway.in_coverage("2024-06-30", "2024-01-01", "2024-06-30") is True
    assert eway.in_coverage("2023-12-31", "2024-01-01", "2024-06-30") is False
    assert eway.in_coverage("2024-07-01", "2024-01-01", "2024-06-30") is False


def test_in_coverage_with_an_unknown_invoice_date():
    # We have no evidence the invoice falls outside the window.
    assert eway.in_coverage(None, "2024-01-01", "2024-06-30") is True


def test_classify_respects_coverage():
    # A missing movement record outside the feed's coverage is not a signal.
    assert eway.classify_mismatch(
        900000, "EWB-X9", None, covered=False) is None
    assert eway.classify_mismatch(
        900000, "EWB-X9", None, covered=True) == eway.MISMATCH_NO_MOVEMENT
    # The other reasons do not depend on the feed's coverage.
    assert eway.classify_mismatch(
        900000, None, None, covered=False) == eway.MISMATCH_NO_REF


def test_every_reason_has_a_label():
    for reason in eway.MISMATCH_REASONS:
        assert eway.describe(reason)
        assert eway.describe(reason) != reason


def test_summarise_counts_by_reason():
    summary = eway.summarise([
        {"reason": eway.MISMATCH_NO_MOVEMENT},
        {"reason": eway.MISMATCH_NO_MOVEMENT},
        {"reason": eway.MISMATCH_AMOUNT},
    ])
    assert "2" in summary and "1" in summary
    assert eway.summarise([]) == ""


def test_render_substitutes_both_fragments():
    query = eway.render("""
    MATCH (t:Transaction)
    /*EWAY_MOVEMENT_JOIN*/
    WITH /*EWAY_MISMATCH_REASON*/ AS reason
    RETURN reason
    """)
    assert "/*EWAY_MOVEMENT_JOIN*/" not in query
    assert "/*EWAY_MISMATCH_REASON*/" not in query
    assert ":EWayBillMovement" in query
    assert "no_movement_record" in query
    # The Cypher's own braces and $placeholders must survive rendering.
    assert "{ref: t.eway_bill_ref}" in query
    assert "$tol_pct" in query


# --- The rule against the live database ------------------------------------


async def _plant(session, company_id, txn_id, amount, ref, movement_amount=None,
                 date="2024-08-01"):
    """Create one invoice (and optionally its movement record) for a test."""
    await session.run("""
    MATCH (c:Company {id: $cid})
    MERGE (t:Transaction {id: $tid})
    SET t.invoice_no = $tid, t.amount = $amount, t.date = date($date),
        t.eway_bill_ref = $ref
    MERGE (c)-[:BILLED]->(t)
    """, cid=company_id, tid=txn_id, amount=amount, ref=ref, date=date)
    if movement_amount is not None:
        await session.run("""
        MERGE (m:EWayBillMovement {ref: $ref})
        SET m.id = $mid, m.amount = $amount, m.source = 'simulated'
        """, ref=ref, mid=f"test-mov-{ref}", amount=movement_amount)


async def _source_coverage(session):
    """The movement-record source's coverage window, as the database has it."""
    result = await session.run("""
    MATCH (s:EWayBillMovementSource {id: 'active'})
    RETURN s.covers_from AS covers_from, s.covers_to AS covers_to
    """)
    row = await result.single()
    if row is None:
        return None, None
    return row["covers_from"], row["covers_to"]


async def _cypher_reason(session, txn_id):
    """Ask the database for the reason code using the SHARED fragment."""
    query = eway.render("""
    MATCH (t:Transaction {id: $tid})
    /*EWAY_MOVEMENT_JOIN*/
    WITH t, m, /*EWAY_MISMATCH_REASON*/ AS reason
    RETURN t.amount AS amount, t.eway_bill_ref AS ref, m.amount AS movement_amount,
           t.date AS date, reason
    """)
    result = await session.run(query, tid=txn_id, **eway.mismatch_params())
    return await result.single()


def test_cypher_rule_agrees_with_python_mirror():
    """The Cypher fragment and the Python mirror must never disagree."""
    from app.deps import get_neo4j_session

    async def _check():
        async with get_neo4j_session() as session:
            result = await session.run(
                "MATCH (c:Company) RETURN c.id AS id LIMIT 1")
            cid = (await result.single())["id"]

            covers_from, covers_to = await _source_coverage(session)
            assert covers_from or covers_to, (
                "the movement-record source declares no coverage window -- "
                "the loader must write one")

            # A date safely inside the source's coverage window.
            inside = str(covers_from or "2024-01-01")
            # A date safely outside it.
            outside = "2019-01-15"

            cases = [
                ("test-tx-noref", 900000, None, None, inside),
                ("test-tx-empty", 900000, "", None, inside),
                ("test-tx-nomov", 900000, "EWB-TEST-NOMOV", None, inside),
                ("test-tx-amount", 800000, "EWB-TEST-AMT", 620000, inside),
                ("test-tx-clean", 900000, "EWB-TEST-CLEAN", 900000, inside),
                ("test-tx-near", 900000, "EWB-TEST-NEAR", 895000, inside),
                # Outside the coverage window: the feed cannot say the record
                # is missing, so nothing may be flagged.
                ("test-tx-outside", 900000, "EWB-TEST-OUT", None, outside),
            ]
            try:
                for txn_id, amount, ref, movement, when in cases:
                    await _plant(session, cid, txn_id, amount, ref, movement, when)
                    rec = await _cypher_reason(session, txn_id)
                    assert rec is not None, txn_id
                    covered = eway.in_coverage(
                        rec["date"], covers_from, covers_to)
                    expected = eway.classify_mismatch(
                        rec["amount"], rec["ref"], rec["movement_amount"],
                        covered=covered)
                    assert rec["reason"] == expected, (
                        f"{txn_id}: cypher said {rec['reason']!r}, "
                        f"python said {expected!r}")
            finally:
                await session.run(
                    "MATCH (t:Transaction) WHERE t.id STARTS WITH 'test-tx-' DETACH DELETE t")
                await session.run(
                    "MATCH (m:EWayBillMovement) WHERE m.id STARTS WITH 'test-mov-' DETACH DELETE m")

    _run(_check())


def test_invoice_outside_the_coverage_window_is_not_flagged():
    """The live rule must not flag an invoice the feed does not cover."""
    from app.deps import get_neo4j_session

    async def _check():
        async with get_neo4j_session() as session:
            result = await session.run(
                "MATCH (c:Company) RETURN c.id AS id LIMIT 1")
            cid = (await result.single())["id"]
            try:
                await _plant(session, cid, "test-tx-oos", 900000,
                             "EWB-TEST-OOS", None, "2019-01-15")
                rec = await _cypher_reason(session, "test-tx-oos")
                assert rec["reason"] is None, (
                    "an invoice outside the feed's coverage window was flagged: "
                    f"{rec['reason']!r}")
            finally:
                await session.run(
                    "MATCH (t:Transaction) WHERE t.id STARTS WITH 'test-tx-' DETACH DELETE t")

    _run(_check())


# --- The consumers ----------------------------------------------------------


async def _mismatch_rows(session, limit=5):
    """High-value invoices without a matching movement record, found with the
    SAME rule the application uses (the shared fragment, not a copy)."""
    query = eway.render(f"""
    MATCH (c:Company)-[:BILLED]->(t:Transaction)
    WHERE t.amount >= $thresh
    /*EWAY_MOVEMENT_JOIN*/
    WITH c, t, m, /*EWAY_MISMATCH_REASON*/ AS reason
    WHERE reason IS NOT NULL
    RETURN c.id AS id, t.id AS tid, t.invoice_no AS invoice_no, reason
    LIMIT $limit
    """)
    result = await session.run(
        query, thresh=settings.eway_high_value_threshold, limit=limit,
        **eway.mismatch_params())
    return await result.data()


def test_explain_reports_the_mismatch_with_its_reason():
    """The explain endpoint must surface the signal and say WHY."""
    from app.deps import get_neo4j_session

    async def _check():
        async with get_neo4j_session() as session:
            rows = await _mismatch_rows(session, limit=1)
            assert rows, (
                "no high-value invoice without a matching movement record was "
                "found -- the sample movement-record source is not loaded")
            row = rows[0]

            explained = await graph_service.explain_entity(session, row["id"])
            mismatches = explained["evidence"]["eway_mismatches"]
            assert mismatches, "the explain endpoint reported no e-Way mismatch"
            hit = next(m for m in mismatches if m["invoice_no"] == row["invoice_no"])
            assert hit["reason"] == row["reason"]
            assert hit["reason_label"]
            assert hit["claimed_ref"] is not None or hit["reason"] == eway.MISMATCH_NO_REF

            reasons = " ".join(explained["reasons"]).lower()
            assert "e-way bill mismatch" in reasons

    _run(_check())


def test_network_flags_the_affected_edges():
    """The network response must flag the edges carrying a mismatching invoice."""
    from app.deps import get_neo4j_session

    async def _check():
        async with get_neo4j_session() as session:
            rows = await _mismatch_rows(session, limit=1)
            assert rows, "no mismatching invoice in the graph"

            network = await graph_service.get_network(session, rows[0]["id"], 2)
            flagged_txn = any(
                e.get("eway_mismatch") for e in network["edges"])
            assert flagged_txn, "no network edge was flagged for the mismatch"
            flagged_node = any(
                n["properties"].get("eway_mismatch") for n in network["nodes"])
            assert flagged_node, "no network node was flagged for the mismatch"

    _run(_check())


def test_feature_counts_the_mismatches():
    """The GNN feature must be a count of unsupported high-value invoices."""
    from app.deps import get_neo4j_session

    async def _check():
        async with get_neo4j_session() as session:
            data = await gnn_features.extract_graph(session)
            companies = data["companies"]
            assert companies, "the feature extractor returned no companies"

            counts = {c["id"]: c.get("eway_mismatch_count", 0) for c in companies}
            assert any(v > 0 for v in counts.values()), (
                "no company shows an e-Way mismatch count -- the feature is dead")

            # Every company whose count is non-zero must have at least that
            # many unsupported high-value invoices, counted independently of
            # the feature extractor's aggregation.
            direct_query = eway.render("""
                MATCH (c:Company {id: $cid})-[:BILLED]->(t:Transaction)
                WHERE t.amount >= $thresh
                /*EWAY_MOVEMENT_JOIN*/
                WITH t, m, /*EWAY_MISMATCH_REASON*/ AS reason
                WHERE reason IS NOT NULL
                RETURN count(t) AS n
                """)
            for cid, count in counts.items():
                if not count:
                    continue
                result = await session.run(
                    direct_query, cid=cid,
                    thresh=settings.eway_high_value_threshold,
                    **eway.mismatch_params())
                row = await result.single()
                assert row["n"] == count, (
                    f"company {cid}: feature says {count}, direct count says {row['n']}")

    _run(_check())


def test_movement_record_source_is_loaded():
    """The simulated movement-record source must exist and be keyed by ref."""
    from app.deps import get_neo4j_session

    async def _check():
        async with get_neo4j_session() as session:
            result = await session.run("""
            MATCH (m:EWayBillMovement)
            RETURN count(m) AS n, count(DISTINCT m.ref) AS refs
            """)
            row = await result.single()
            assert row["n"] > 0, "no e-Way Bill movement records were loaded"
            assert row["n"] == row["refs"], "movement records are not uniquely keyed by ref"

            # Every movement record must carry the fields the explain
            # endpoint reports on.
            result = await session.run("""
            MATCH (m:EWayBillMovement)
            WHERE m.amount IS NULL OR m.ref IS NULL
            RETURN count(m) AS n
            """)
            bad = await result.single()
            assert bad["n"] == 0, "movement records are missing ref/amount"

    _run(_check())


def test_heuristic_score_credits_the_e_way_signal():
    """A company with unsupported high-value invoices scores higher than one
    without -- the signal has to actually move the score."""
    base = {
        "cycle_count": 0, "degree": 1, "shared_director_count": 0,
        "shared_address_count": 0, "pagerank": 0.01, "betweenness": 0.0,
        "eway_mismatch_count": 0, "burst_count": 0,
    }
    flagged = dict(base, eway_mismatch_count=3)
    assert graph_service._heuristic_risk_score(flagged) > graph_service._heuristic_risk_score(base)
