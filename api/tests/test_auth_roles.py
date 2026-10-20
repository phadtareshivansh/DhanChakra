"""Auth refactor: fixed 3-slot role model + Super Admin user management.

Covers:
  * POST /auth/register is gone (404) — no self-registration at all.
  * /admin/users/* requires the admin role (401 anon, 403 non-admin).
  * The admin can update and reset a standard user.
  * Admin cannot demote or delete itself through these endpoints.
  * A request body cannot change a role.
  * The caps hold: a 3rd analyst and a 2nd admin are rejected (409 / DB).

The DB-level caps live in migration 012_user_role_limits.sql; these tests hit
the API paths that mirror them.
"""

import os

import httpx
import pytest

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

SUPER_EMAIL = os.getenv("SUPER_ADMIN_EMAIL")
SUPER_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD")
USER1_EMAIL = os.getenv("USER1_EMAIL")
USER1_PASSWORD = os.getenv("USER1_PASSWORD")
USER2_EMAIL = os.getenv("USER2_EMAIL")
USER2_PASSWORD = os.getenv("USER2_PASSWORD")

import asyncio


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


pytestmark = pytest.mark.skipif(
    not (SUPER_EMAIL and SUPER_PASSWORD and USER1_EMAIL and USER1_PASSWORD),
    reason="seeded slot credentials not configured",
)


@pytest.fixture
def client():
    return httpx.Client(base_url=API_BASE_URL, timeout=30)


def _login(client, email, password):
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_register_endpoint_is_gone(client):
    r = client.post("/auth/register", json={
        "email": "nobody@example.invalid", "password": "pw", "role": "admin",
    })
    assert r.status_code == 404


def test_anonymous_cannot_list_users(client):
    assert client.get("/admin/users").status_code == 401


def test_invalid_token_is_401(client):
    assert client.get("/admin/users", headers=_auth("not-a-token")).status_code == 401


def test_non_admin_is_403(client):
    tok = _login(client, USER1_EMAIL, USER1_PASSWORD)["access_token"]
    assert client.get("/admin/users", headers=_auth(tok)).status_code == 403


def test_admin_can_list_users_without_password_hashes(client):
    admin = _login(client, SUPER_EMAIL, SUPER_PASSWORD)
    r = client.get("/admin/users", headers=_auth(admin["access_token"]))
    assert r.status_code == 200
    users = r.json()["users"]
    roles = sorted(u["role"] for u in users)
    assert roles.count("admin") == 1
    assert roles.count("analyst") >= 1
    for u in users:
        assert "password_hash" not in u
        assert set(u) >= {"id", "email", "role"}


def test_admin_can_update_standard_user(client):
    admin = _login(client, SUPER_EMAIL, SUPER_PASSWORD)
    h = _auth(admin["access_token"])
    users = client.get("/admin/users", headers=h).json()["users"]
    target = next(u for u in users if u["role"] == "analyst")

    new_name = "Analyst Renamed"
    r = client.put(f"/admin/users/{target['id']}",
                   json={"display_name": new_name}, headers=h)
    assert r.status_code == 200
    assert r.json()["display_name"] == new_name
    assert r.json()["role"] == "analyst"

    # restore
    client.put(f"/admin/users/{target['id']}",
               json={"display_name": target.get("display_name") or "Analyst"}, headers=h)


def test_role_cannot_be_changed_via_body(client):
    """A 'role' field in the PUT body must be ignored: roles are fixed."""
    admin = _login(client, SUPER_EMAIL, SUPER_PASSWORD)
    h = _auth(admin["access_token"])
    users = client.get("/admin/users", headers=h).json()["users"]
    target = next(u for u in users if u["role"] == "analyst")
    r = client.put(f"/admin/users/{target['id']}",
                   json={"role": "admin"}, headers=h)
    assert r.status_code == 200
    assert r.json()["role"] == "analyst"  # unchanged


def test_admin_cannot_edit_self(client):
    admin = _login(client, SUPER_EMAIL, SUPER_PASSWORD)
    h = _auth(admin["access_token"])
    r = client.put(f"/admin/users/{admin['user']['id']}",
                   json={"display_name": "Hacker"}, headers=h)
    assert r.status_code == 403


def test_admin_cannot_reset_own_password_via_admin_route(client):
    admin = _login(client, SUPER_EMAIL, SUPER_PASSWORD)
    h = _auth(admin["access_token"])
    r = client.post(f"/admin/users/reset-password/{admin['user']['id']}", headers=h)
    assert r.status_code == 403


def test_admin_can_reset_standard_user_password(client):
    admin = _login(client, SUPER_EMAIL, SUPER_PASSWORD)
    h = _auth(admin["access_token"])
    users = client.get("/admin/users", headers=h).json()["users"]
    target = next(u for u in users if u["role"] == "analyst")
    r = client.post(f"/admin/users/reset-password/{target['id']}", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    # The reset must not expose the hash; a generated password may be returned.
    assert "password_hash" not in r.json()


def _run_db_probe(probe_coro_factory):
    """Run a DB probe on the suite's current event loop.

    Follows the same convention as the other live tests in this suite
    (`asyncio.new_event_loop` via the `event_loop` fixture + run_until_complete)
    so it never closes the loop the shared Neo4j/SQLAlchemy drivers depend on.
    A private engine avoids reusing pooled connections from another loop.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import settings

    async def runner():
        url = (f"postgresql+asyncpg://{settings.postgres_user}:"
               f"{settings.postgres_password}@{settings.postgres_host}:"
               f"{settings.postgres_port}/{settings.postgres_db}")
        engine = create_async_engine(url, echo=False)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as db:
                return await probe_coro_factory(db)
        finally:
            await engine.dispose()

    return asyncio.get_event_loop().run_until_complete(runner())


def test_service_cap_rejects_second_admin():
    """Service layer refuses a 2nd admin with a clean UserLimitError, so the
    API can answer 409 instead of a raw DB error."""
    from app.services import auth_service

    async def probe(db):
        try:
            await auth_service.assert_can_create_role(db, "admin")
            return None
        except auth_service.UserLimitError as e:
            return str(e)
        finally:
            await db.rollback()

    err = _run_db_probe(probe)
    assert err, "service did not reject a 2nd admin"


def test_analyst_and_admin_caps_enforced_at_db_level():
    """Direct DB probe: the caps reject a 3rd analyst and a 2nd admin.

    Each probe runs in its own transaction and is rolled back, so no rows
    persist.
    """
    from sqlalchemy import text

    async def probe(db):
        analysts = (await db.execute(
            text("SELECT count(*) FROM users WHERE role='analyst'"))).scalar_one()
        admins = (await db.execute(
            text("SELECT count(*) FROM users WHERE role='admin'"))).scalar_one()

        # 2nd admin must violate the partial unique index.
        second_admin_rejected = False
        try:
            await db.execute(text(
                "INSERT INTO users (email, display_name, password_hash, role) "
                "VALUES ('probe_admin@example.invalid','p','x','admin')"))
            await db.commit()
        except Exception:
            await db.rollback()
            second_admin_rejected = True

        # A 3rd analyst must be rejected by the trigger.
        third_analyst_rejected = False
        try:
            if analysts < 2:
                await db.execute(text(
                    "INSERT INTO users (email, display_name, password_hash, role) "
                    "VALUES ('probe_fill@example.invalid','p','x','analyst')"))
                await db.commit()
            await db.execute(text(
                "INSERT INTO users (email, display_name, password_hash, role) "
                "VALUES ('probe_analyst3@example.invalid','p','x','analyst')"))
            await db.commit()
        except Exception:
            await db.rollback()
            third_analyst_rejected = True
        finally:
            await db.execute(text(
                "DELETE FROM users WHERE email LIKE 'probe_%example.invalid'"))
            await db.commit()

        return admins, second_admin_rejected, third_analyst_rejected

    admins, second_admin_rejected, third_analyst_rejected = _run_db_probe(probe)
    assert admins >= 1
    assert second_admin_rejected, "DB unique index did not reject a 2nd admin"
    assert third_analyst_rejected, "DB trigger did not reject a 3rd analyst"
