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


def test_loops(client):
    r = client.get("/analytics/loops", params={"max_length": 6})
    assert r.status_code == 200
    assert r.json()["total"] >= 1


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
