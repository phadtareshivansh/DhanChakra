"""P2.2 collaboration API tests — run against the live stack.

Usage:
    docker compose exec api pytest tests/test_collaboration.py -q

These cover the worklist bulk actions, case comments/activity/entities,
assignable users and entity notes/history added for the core-screen redesign.
"""

import os

import httpx
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD")

pytestmark = pytest.mark.skipif(
    not (ADMIN_EMAIL and ADMIN_PASSWORD),
    reason="SUPER_ADMIN_* not configured",
)


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=API_BASE_URL, timeout=30)


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def a_cin(client):
    r = client.get("/worklist", params={"page": 1, "page_size": 1})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items, "worklist is empty; bootstrap demo data first"
    return items[0]["cin"]


@pytest.fixture(scope="module")
def a_case(client):
    r = client.post("/cases", json={
        "title": "P2.2 collaboration fixture",
        "description": "created by test_collaboration.py",
        "priority": 1,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_assignable_users_requires_auth(client):
    assert client.get("/users/assignable").status_code == 401


def test_assignable_users_lists_people(client, auth):
    r = client.get("/users/assignable", headers=auth)
    assert r.status_code == 200, r.text
    users = r.json()
    assert users
    assert {"id", "email", "role"} <= set(users[0])
    assert all("password" not in key for key in users[0])


def test_worklist_facets(client):
    r = client.get("/worklist/facets")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["states"], list)
    assert isinstance(body["sectors"], list)
    assert body["risk_bands"]["critical"] >= body["risk_bands"]["high"] >= body["risk_bands"]["medium"]


def test_has_cycles_filter(client):
    r = client.get("/worklist", params={"has_cycles": True, "page_size": 100})
    assert r.status_code == 200, r.text
    for item in r.json()["items"]:
        assert (item.get("cycle_count") or 0) >= 1


def test_worklist_search_filter(client, a_cin):
    r = client.get("/worklist", params={"q": a_cin, "page_size": 10})
    assert r.status_code == 200, r.text
    assert any(item["cin"] == a_cin for item in r.json()["items"])
    assert client.get("/worklist", params={"q": "no-such-entity-xyz"}).json()["total"] == 0


def test_case_can_be_created_with_assignee_and_unassigned(client, auth, a_case):
    me = client.get("/auth/me", headers=auth).json()
    r = client.post("/cases", json={"title": "Assigned fixture", "assignee_id": me["id"]})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["assignee_id"] == me["id"]

    r = client.patch(f"/cases/{created['id']}", json={"assignee_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["assignee_id"] is None


def test_case_comments_and_activity(client, auth, a_case):
    case_id = a_case["id"]
    r = client.post(f"/cases/{case_id}/comments", headers=auth, json={"body": "Suspicious ring, escalating."})
    assert r.status_code == 201, r.text
    comment = r.json()
    assert comment["body"] == "Suspicious ring, escalating."
    assert comment["author_name"]

    r = client.get(f"/cases/{case_id}/comments")
    assert r.status_code == 200
    assert any(c["id"] == comment["id"] for c in r.json())

    r = client.get(f"/cases/{case_id}/activity")
    assert r.status_code == 200
    actions = {entry["action"] for entry in r.json()}
    assert "created" in actions
    assert "commented" in actions


def test_case_update_is_logged(client, a_case):
    case_id = a_case["id"]
    r = client.patch(f"/cases/{case_id}", json={"status": "in_progress"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"
    activity = client.get(f"/cases/{case_id}/activity").json()
    assert any(entry["action"] == "status_changed" for entry in activity)


def test_bulk_add_entities_to_case(client, auth, a_case, a_cin):
    case_id = a_case["id"]
    r = client.post("/worklist/bulk", headers=auth, json={
        "action": "add_to_case", "entity_cins": [a_cin], "case_id": case_id,
    })
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == 1

    entities = client.get(f"/cases/{case_id}/entities").json()
    assert any(e["entity_cin"] == a_cin for e in entities)

    r = client.delete(f"/cases/{case_id}/entities/{a_cin}", headers=auth)
    assert r.status_code == 204, r.text
    entities = client.get(f"/cases/{case_id}/entities").json()
    assert all(e["entity_cin"] != a_cin for e in entities)


def test_bulk_assign_and_assignments(client, auth, a_cin):
    me = client.get("/auth/me", headers=auth).json()
    r = client.post("/worklist/bulk", headers=auth, json={
        "action": "assign", "entity_cins": [a_cin], "assignee_id": me["id"],
    })
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == 1

    r = client.get("/worklist/assignments", params={"cins": a_cin})
    assert r.status_code == 200
    rows = r.json()
    assert rows and rows[0]["assignee_id"] == me["id"]
    assert rows[0]["assignee_name"]


def test_bulk_label_is_stored(client, auth, a_cin):
    r = client.post("/worklist/bulk", headers=auth, json={
        "action": "label", "entity_cins": [a_cin], "label": "needs_review",
    })
    assert r.status_code == 200, r.text
    assert r.json()["affected"] == 1
    feedback = client.get(f"/entities/{a_cin}/feedback").json()
    assert any(f["label"] == "needs_review" for f in feedback)


def test_bulk_rejects_invalid_action(client, auth, a_cin):
    r = client.post("/worklist/bulk", headers=auth, json={
        "action": "delete_everything", "entity_cins": [a_cin],
    })
    assert r.status_code == 422


def test_entity_notes_and_history(client, auth, a_cin):
    r = client.post(f"/entities/{a_cin}/notes", headers=auth, json={"body": "Director linked to two shell companies."})
    assert r.status_code == 201, r.text
    note = r.json()
    assert note["entity_cin"] == a_cin

    notes = client.get(f"/entities/{a_cin}/notes").json()
    assert any(n["id"] == note["id"] for n in notes)

    history = client.get(f"/entities/{a_cin}/history").json()
    assert history["entity_cin"] == a_cin
    assert any(e["kind"] == "note" for e in history["events"])
    assert any(e["kind"] == "feedback" for e in history["events"])
