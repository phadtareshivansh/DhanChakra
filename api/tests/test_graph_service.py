"""Unit tests for the graph algorithm service layer (TRD §9).
Runs against the live Neo4j instance via the API container's environment,
or directly with pytest against a running stack.

Usage: docker exec dhanchakra-api pytest tests -q
"""

import asyncio
import pytest
import sys
import os

sys.path.insert(0, "/app/app")

from services import graph_service


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_heuristic_risk_score_cycle_dominant():
    score = graph_service._heuristic_risk_score({
        "cycle_count": 2, "degree": 2, "shared_director_count": 3,
        "shared_address_count": 2, "pagerank": 0.2, "betweenness": 0.1,
    })
    assert 40 <= score <= 100
    assert score >= 60


def test_heuristic_risk_score_clean():
    score = graph_service._heuristic_risk_score({
        "cycle_count": 0, "degree": 1, "shared_director_count": 0,
        "shared_address_count": 0, "pagerank": 0.01, "betweenness": 0.0,
    })
    assert score < 40


def test_heuristic_risk_score_always_bounded():
    score = graph_service._heuristic_risk_score({
        "cycle_count": 50, "degree": 100, "shared_director_count": 50,
        "shared_address_count": 50, "pagerank": 5.0, "betweenness": 5.0,
    })
    assert score <= 100.0


def test_graph_services_live():
    """End-to-end against the seeded graph (hero ring must be detected)."""
    from app.deps import get_neo4j_session

    async def _check():
        async with get_neo4j_session() as session:
            search = await graph_service.search_entities(session, "Orbit", 5)
            assert len(search) >= 1
            assert search[0]["name"] == "Orbit Logistics Pvt Ltd"

            loops = await graph_service.get_loops(session, 6)
            assert loops["total"] >= 1
            assert loops["loops"][0]["length"] >= 2

            stats = await graph_service.get_stats_overview(session, None)
            assert stats["companies"] >= 6

    _run(_check())
