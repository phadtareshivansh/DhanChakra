"""Phase 2 unit tests: entity resolution (Backend Schema §2.2, Implementation
Plan Phase 2). Pure-python units run anywhere; live tests run against the
running Neo4j stack (they create + clean up their own fixture subgraph).

Usage: docker exec dhanchakra-api pytest /tmp/tests/test_entity_resolution.py -q
"""

import asyncio
import sys

import pytest

sys.path.insert(0, "/app/app")

from services import graph_service


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# --- Pure-python: Jaro-Winkler ---

def test_jaro_winkler_identical():
    assert graph_service._jaro_winkler("Vertex Analytics Pvt Ltd", "Vertex Analytics Pvt Ltd") == 1.0


def test_jaro_winkler_punctuation_variant():
    score = graph_service._jaro_winkler("Vertex Analytics Pvt Ltd", "Vertex Analytics Pvt. Ltd.")
    assert score >= 0.92


def test_jaro_winkler_case_insensitive():
    assert graph_service._jaro_winkler("ORBIT LOGISTICS", "orbit logistics") == 1.0


def test_jaro_winkler_unrelated_low():
    score = graph_service._jaro_winkler("Vertex Analytics Pvt Ltd", "CloudNine IT Services")
    assert score < 0.92


def test_jaro_winkler_empty_inputs():
    assert graph_service._jaro_winkler("", "Vertex") == 0.0
    assert graph_service._jaro_winkler("x", "") == 0.0


def test_jaro_winkler_no_common_chars():
    assert graph_service._jaro_winkler("abc", "xyz") == 0.0


# --- Pure-python: cycle canonicalization ---

def test_canonical_cycle_rotations_equal():
    a = graph_service._canonical_cycle(["x", "y", "z"])
    b = graph_service._canonical_cycle(["y", "z", "x"])
    c = graph_service._canonical_cycle(["z", "x", "y"])
    d = graph_service._canonical_cycle(["z", "y", "x"])
    assert a == b == c == d


def test_canonical_cycle_different_rings_differ():
    a = graph_service._canonical_cycle(["x", "y", "z"])
    b = graph_service._canonical_cycle(["x", "y", "z", "w"])
    assert a != b


# --- Live: deterministic + fuzzy resolution against Neo4j ---

FIXTURE_CINS = [
    "FIXTURE2026TEST000001",
    "FIXTURE2026TEST000002",
    "FIXTURE2026TEST000003",
    "FIXTURE2026TEST000004",
]


@pytest.fixture
def resolution_fixture():
    """Create two near-identical shells (shared DIN/address/bank) and two
    fuzzy-only shells; yields cleanup."""
    from app.deps import get_neo4j_session

    async def _setup():
        async with get_neo4j_session() as session:
            await session.run("""
            MERGE (d1:Director {din: '99999999'})
            SET d1.name = 'Fixture Director', d1.id = 'dir-fixture-1'
            MERGE (d2:Director {din: '99999998'})
            SET d2.name = 'Other Director', d2.id = 'dir-fixture-2'
            MERGE (a1:Address {id: 'addr-fixture-1'})
            SET a1.raw_address = '1 Fixture Road', a1.normalized_address = '1 fixture road|maharashtra'
            MERGE (a2:Address {id: 'addr-fixture-2'})
            SET a2.raw_address = '2 Other Road', a2.normalized_address = '2 other road|delhi'
            MERGE (b1:BankAccount {id: 'bank-fixture-1'})
            SET b1.ifsc = 'FIXT0000001', b1.account_hash = 'acct-fixture-1'
            MERGE (b2:BankAccount {id: 'bank-fixture-2'})
            SET b2.ifsc = 'FIXT0000002', b2.account_hash = 'acct-fixture-2'
            MERGE (c1:Company {cin: 'FIXTURE2026TEST000001'})
            SET c1.id = 'fixture-1', c1.name = 'Fixture Shell One Pvt Ltd'
            MERGE (c2:Company {cin: 'FIXTURE2026TEST000002'})
            SET c2.id = 'fixture-2', c2.name = 'Fixture Shell One Pvt. Ltd.'
            MERGE (c3:Company {cin: 'FIXTURE2026TEST000003'})
            SET c3.id = 'fixture-3', c3.name = 'Fixture Shell One Pvt Ltd'
            MERGE (c4:Company {cin: 'FIXTURE2026TEST000004'})
            SET c4.id = 'fixture-4', c4.name = 'Totally Unrelated Ventures'
            """)
            await session.run("""
            MATCH (c1:Company {cin: 'FIXTURE2026TEST000001'})
            MATCH (c2:Company {cin: 'FIXTURE2026TEST000002'})
            MATCH (d1:Director {din: '99999999'}), (d2:Director {din: '99999998'})
            MATCH (a1:Address {id: 'addr-fixture-1'}), (a2:Address {id: 'addr-fixture-2'})
            MATCH (b1:BankAccount {id: 'bank-fixture-1'}), (b2:BankAccount {id: 'bank-fixture-2'})
            CREATE (d1)-[:DIRECTOR_OF]->(c1), (d1)-[:DIRECTOR_OF]->(c2)
            CREATE (d2)-[:DIRECTOR_OF]->(c3)
            CREATE (c1)-[:REGISTERED_AT]->(a1), (c2)-[:REGISTERED_AT]->(a1)
            CREATE (c3)-[:REGISTERED_AT]->(a2), (c4)-[:REGISTERED_AT]->(a2)
            CREATE (c1)-[:OPERATES_ACCOUNT]->(b1), (c2)-[:OPERATES_ACCOUNT]->(b1)
            CREATE (c3)-[:OPERATES_ACCOUNT]->(b2)
            """)

    async def _teardown():
        async with get_neo4j_session() as session:
            await session.run(
                "MATCH (n) WHERE n.cin IN $cins DETACH DELETE n",
                cins=FIXTURE_CINS,
            )
            await session.run(
                "MATCH (n) WHERE n.id STARTS WITH 'addr-fixture-' "
                "OR n.id STARTS WITH 'bank-fixture-' "
                "OR n.id STARTS WITH 'dir-fixture-' DETACH DELETE n"
            )

    _run(_setup())
    yield
    _run(_teardown())


def test_resolution_live(resolution_fixture):
    from app.deps import get_neo4j_session

    async def _check():
        async with get_neo4j_session() as session:
            summary = await graph_service.run_entity_resolution(session, fuzzy_threshold=0.92)
            assert summary["deterministic"] >= 3
            assert summary["fuzzy"] >= 1

            # First run created fixture edges; second run must be idempotent
            summary2 = await graph_service.run_entity_resolution(session, fuzzy_threshold=0.92)
            assert summary2["resolved_edges"] == 0

            res = await session.run("""
            MATCH (a:Company)-[r:RESOLVED_AS]->(b:Company)
            WHERE a.cin IN $cins AND b.cin IN $cins
            RETURN DISTINCT r.method AS method, r.key_type AS key_type, r.confidence AS confidence
            """, cins=FIXTURE_CINS)
            edges = await res.data()
            methods = {(e["method"], e["key_type"]) for e in edges}
            assert ("deterministic", "din") in methods
            assert ("deterministic", "address") in methods
            assert ("deterministic", "bank") in methods
            assert ("fuzzy", "name_similarity") in methods

            fuzzy = [e for e in edges if e["method"] == "fuzzy"]
            assert all(e["confidence"] is not None and e["confidence"] >= 0.92 for e in fuzzy)

    _run(_check())