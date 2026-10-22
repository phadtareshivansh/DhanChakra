"""P2.3 graph workspace API tests — run against the live stack.

Usage:
    docker compose exec api pytest tests/test_graph_workspace.py -q
"""

import os

import httpx
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=API_BASE_URL, timeout=60)


@pytest.fixture(scope="module")
def companies(client):
    response = client.get("/worklist", params={"page": 1, "page_size": 8})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    ring = [item for item in items if item.get("cycle_count")]
    assert len(ring) >= 2, "need at least two ring companies; bootstrap demo data first"
    return ring


def test_network_edges_carry_invoice_dates(client, companies):
    response = client.get(f"/entities/{companies[0]['cin']}/network", params={"hops": 2})
    assert response.status_code == 200, response.text
    edges = response.json()["edges"]
    dated = [edge for edge in edges if edge.get("date")]
    assert dated, "invoice edges should expose the transaction date"
    assert all(len(edge["date"]) == 10 for edge in dated)


def test_network_timeline_buckets(client, companies):
    response = client.get(
        f"/entities/{companies[0]['cin']}/network/timeline",
        params={"hops": 2, "bucket": "month"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["start"] and body["end"]
    assert body["bucket"] == "month"
    assert body["buckets"]
    assert sum(bucket["count"] for bucket in body["buckets"]) >= 1
    assert all(bucket["amount"] >= 0 for bucket in body["buckets"])


def test_network_timeline_weekly_bucket(client, companies):
    response = client.get(
        f"/entities/{companies[0]['cin']}/network/timeline",
        params={"hops": 2, "bucket": "week"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["bucket"] == "week"
    assert all("-W" in bucket["period"] for bucket in body["buckets"])


def test_network_timeline_rejects_unknown_bucket(client, companies):
    response = client.get(
        f"/entities/{companies[0]['cin']}/network/timeline",
        params={"hops": 2, "bucket": "day"},
    )
    assert response.status_code == 422


def test_shortest_paths_returns_nodes_edges_and_summaries(client, companies):
    response = client.get(
        "/graph/paths",
        params={
            "source": companies[0]["cin"],
            "target": companies[1]["cin"],
            "max_length": 6,
            "limit": 5,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["paths"], "ring companies should be connected"
    node_ids = {node["id"] for node in body["nodes"]}
    for path in body["paths"]:
        assert path["length"] >= 1
        assert path["node_ids"][0] in node_ids
        assert path["node_ids"][-1] in node_ids
        assert len(path["node_ids"]) == path["length"] + 1
    # allShortestPaths can yield the same undirected path twice; dedupe in the
    # service so API consumers see distinct summaries.
    signatures = [tuple(path["node_ids"]) for path in body["paths"]]
    assert len(signatures) == len(set(signatures))


def test_shortest_paths_rejects_same_entity(client, companies):
    response = client.get(
        "/graph/paths",
        params={"source": companies[0]["cin"], "target": companies[0]["cin"]},
    )
    assert response.status_code == 422


def test_shortest_paths_missing_entity_is_not_found(client, companies):
    response = client.get(
        "/graph/paths",
        params={"source": companies[0]["cin"], "target": "DOES-NOT-EXIST"},
    )
    assert response.status_code == 404
