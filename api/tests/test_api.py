"""API integration tests (TRD §9) — run against the live stack.

Usage:
    docker compose exec api pytest tests -q
"""

import os
import pytest
import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
API_ROOT_URL = API_BASE_URL.split("/api/")[0]

ADMIN_EMAIL = os.getenv("DEMO_ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD")


@pytest.fixture
def client():
    return httpx.Client(base_url=API_BASE_URL, timeout=30)


def test_health(client):
    r = httpx.get(f"{API_ROOT_URL}/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.skipif(not (ADMIN_EMAIL and ADMIN_PASSWORD), reason="DEMO_ADMIN_* not configured")
def test_login_flow(client):
    r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200
    data = r.json()
    assert data["access_token"]


@pytest.mark.skipif(not (ADMIN_EMAIL and ADMIN_PASSWORD), reason="DEMO_ADMIN_* not configured")
def test_login_wrong_password(client):
    r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert r.status_code == 401


def test_search(client):
    r = client.get("/entities/search", params={"q": "Orbit"})
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_entity_detail(client):
    r = client.get("/entities/search", params={"q": "Orbit"})
    entity_id = r.json()["results"][0]["id"]
    r2 = client.get(f"/entities/{entity_id}")
    assert r2.status_code == 200
    assert r2.json()["name"] == "Orbit Logistics Pvt Ltd"


def test_network(client):
    r = client.get("/entities/search", params={"q": "Orbit"})
    entity_id = r.json()["results"][0]["id"]
    r2 = client.get(f"/entities/{entity_id}/network", params={"hops": 2})
    assert r2.status_code == 200
    assert len(r2.json()["nodes"]) >= 3


def test_explain_flagged(client):
    r = client.get("/entities/search", params={"q": "Orbit"})
    entity_id = r.json()["results"][0]["id"]
    r2 = client.get(f"/entities/{entity_id}/explain")
    assert r2.status_code == 200
    body = r2.json()
    assert len(body["reasons"]) >= 1


def test_explain_hero_ring_evidence(client):
    """The hero ring's /explain must return REAL evidence derived from the
    detected FraudCycle: 6 hops, 6 companies, the 6 invoices, the shared
    director/address, and the attribution method label."""
    r = client.get("/entities/search", params={"q": "Maya Infra"})
    entity_id = r.json()["results"][0]["id"]
    body = client.get(f"/entities/{entity_id}/explain").json()
    ev = body["evidence"]
    assert ev["method"] == "subgraph_attribution"  # not GNNExplainer
    assert len(ev["cycles"]) >= 1
    cycle = ev["cycles"][0]
    assert cycle["hop_count"] == 6
    assert cycle["company_count"] == 6
    assert cycle["total_invoice_amount"] == 5300000.0
    assert len(cycle["invoices"]) == 6
    assert cycle["date_span"]["span_days"] == 10
    assert {c["cin"] for c in cycle["companies"]} == {
        "L12345MH2023PLC900001", "L12345MH2023PLC900002", "L12345MH2023PLC900003",
        "L12345MH2023PLC900004", "L12345MH2023PLC900005", "L12345MH2023PLC900006",
    }
    assert any(sd["director"] == "Rakesh Malhotra" for sd in ev["shared_directors"])
    assert any(sa["address"] == "12 Vasant Vihar Lane" for sa in ev["shared_addresses"])
    assert len(ev["communities"]) >= 1
    assert ev["risk_decomposition"]["cycle"] > 0
    # reason is generated from real values, not a placeholder
    joined = " ".join(body["reasons"])
    assert "6-hop" in joined and "5,300,000" in joined


def test_explain_no_evidence_is_honest(client):
    """A clean control company must report honestly, with empty evidence
    arrays and no invented cycle."""
    r = client.get("/entities/search", params={"q": "Harbor"})
    results = r.json()["results"]
    if not results:
        pytest.skip("clean control company not present")
    body = client.get(f"/entities/{results[0]['id']}/explain").json()
    assert body["evidence"]["cycles"] == []
    assert body["reasons"]


def test_loops(client):
    r = client.get("/analytics/loops", params={"max_length": 6})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    # Hero ring: 6 companies in a closed loop => 6 invoice edges / hops.
    hero = next((l for l in body["loops"] if "Maya Infra Projects Pvt Ltd" in [c.get("name") for c in l["companies"]]), None)
    assert hero is not None, "hero ring not found in /analytics/loops"
    assert hero["length"] == 6, f"expected hop_count 6, got {hero['length']}"
    assert hero["total_amount"] == 5300000.0


def test_worklist(client):
    r = client.get("/worklist", params={"sort": "risk_score", "direction": "desc"})
    assert r.status_code == 200
    data = r.json()
    assert "items" in data
    assert data["total"] >= 1


def test_stats_overview(client):
    r = client.get("/stats/overview")
    assert r.status_code == 200
    assert r.json()["companies"] >= 6


def test_cases_crud(client):
    create = client.post("/cases", json={
        "title": "Test case",
        "description": "automated test",
        "company_cin": "L12345KA2024PLC888999",
        "priority": 1,
    })
    assert create.status_code == 201
    case_id = create.json()["id"]

    detail = client.get(f"/cases/{case_id}")
    assert detail.status_code == 200

    update = client.patch(f"/cases/{case_id}", json={"status": "in_progress"})
    assert update.status_code == 200
    assert update.json()["status"] == "in_progress"

    export = client.post(f"/cases/{case_id}/export")
    assert export.status_code == 200
    assert export.json()["payload"]["entity"]["cin"] == "L12345KA2024PLC888999"

    delete = client.delete(f"/cases/{case_id}")
    assert delete.status_code == 204


def test_ingestion_validation(client):
    r = client.post("/ingest/csv", data={"source": "bogus"})
    assert r.status_code == 422
