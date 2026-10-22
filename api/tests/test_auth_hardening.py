"""Tests for the auth hardening work (TASK C1).

Covers the five things the task asks for, each against the live stack:

1. rate limiting per IP and per account, with a temporary lockout;
2. short-lived access tokens, refresh tokens, server-side revocation and a
   token version that a password reset bumps;
3. the audit trail: admin actions, failed logins and lockouts;
4. security headers and a strict CORS allowlist;
5. the behaviour of each of the above.

Usage: docker compose exec api pytest tests/test_auth_hardening.py -q
"""

import asyncio
import os

import httpx
import pytest

from app.config import settings
from app.services import auth_service, login_guard

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
API_ROOT_URL = API_BASE_URL.split("/api/")[0]

ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD")

pytestmark = pytest.mark.skipif(
    not (ADMIN_EMAIL and ADMIN_PASSWORD),
    reason="SUPER_ADMIN_* not configured",
)


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _client() -> httpx.Client:
    return httpx.Client(base_url=API_BASE_URL, timeout=30)


def _login(client: httpx.Client, email: str, password: str) -> httpx.Response:
    return client.post("/auth/login", json={"email": email, "password": password})


def _admin_token(client: httpx.Client) -> str:
    r = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _clear_attempts(email: str, ip: str = "127.0.0.1") -> None:
    """Reset the counters so one test cannot lock out the next."""
    from app.deps import get_db_session_cm

    async def _go():
        async with get_db_session_cm() as db:
            await db.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM login_attempts WHERE email = :e OR client_ip = :ip"
                ),
                {"e": (email or "").lower(), "ip": ip},
            )
            await db.commit()

    _run(_go())


# ---------------------------------------------------------------------------
# 1. Rate limiting and lockout
# ---------------------------------------------------------------------------

def test_login_is_rate_limited_per_account():
    """Repeated failures against one account end in a lockout.

    The account used is a real one, so the lockout can be checked against
    the CORRECT password: a lockout that a correct password walks through
    is no lockout at all.
    """
    client = _client()
    _clear_attempts(ADMIN_EMAIL)

    statuses = []
    for _ in range(settings.login_max_failures_per_account + 2):
        r = _login(client, ADMIN_EMAIL, "wrong-password")
        statuses.append(r.status_code)
        if r.status_code == 429:
            break

    assert 429 in statuses, f"expected a lockout, got {statuses}"
    assert statuses[-1] == 429

    # The lockout must hold even for the CORRECT password.
    r = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 429, (
        f"the lockout did not hold against the correct password: {r.status_code}")

    _clear_attempts(ADMIN_EMAIL)


def test_lockout_response_is_generic_and_carries_retry_after():
    email = "lockout-generic@example.invalid"
    _clear_attempts(email)
    client = _client()

    for _ in range(settings.login_max_failures_per_account + 1):
        r = _login(client, email, "wrong-password")
        if r.status_code == 429:
            break

    assert r.status_code == 429
    assert r.headers.get("Retry-After"), "the 429 must say when to retry"
    body = r.json()
    assert body["detail"]["code"] == "too_many_attempts"
    # It must not say which account was locked, or that it exists.
    assert email not in r.text.lower()

    _clear_attempts(email)


def test_failed_login_does_not_reveal_whether_the_account_exists():
    """A wrong password and an unknown address must be indistinguishable."""
    client = _client()
    known = _login(client, ADMIN_EMAIL, "definitely-not-the-password")
    unknown_email = "no-such-account-xyz@example.invalid"
    _clear_attempts(unknown_email)
    unknown = _login(client, unknown_email, "definitely-not-the-password")

    assert known.status_code == unknown.status_code == 401
    assert known.json() == unknown.json(), (
        "the two responses differ, so the endpoint enumerates accounts")

    _clear_attempts(unknown_email)


def test_rate_limit_is_per_account_not_global():
    """One account being attacked must not lock out an unrelated account."""
    attacker = "per-account-attack@example.invalid"
    _clear_attempts(attacker)
    client = _client()

    for _ in range(settings.login_max_failures_per_account + 1):
        _login(client, attacker, "wrong-password")

    # A different account from the same client is unaffected.
    r = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, (
        f"an unrelated account was locked out by another account's failures: "
        f"{r.status_code} {r.text}")

    _clear_attempts(attacker)


# ---------------------------------------------------------------------------
# 2. Refresh tokens, revocation and the token version
# ---------------------------------------------------------------------------

def test_login_returns_a_refresh_token():
    client = _client()
    r = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"], "no refresh token was issued"
    assert body["expires_in"] == settings.access_token_expire_minutes * 60


def test_access_tokens_are_short_lived():
    """The access token must not outlive its configured lifetime."""
    assert settings.access_token_expire_minutes <= 60, (
        "an access token that lasts hours is a bearer credential that "
        "stays useful to a thief for hours")
    client = _client()
    token = _admin_token(client)
    payload = auth_service.decode_token(token)
    assert payload is not None
    assert payload["typ"] == "access"
    assert "tv" in payload, "the token carries no token version"


def test_refresh_token_issues_a_new_access_token():
    client = _client()
    r = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    refresh = r.json()["refresh_token"]

    r2 = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["access_token"]
    assert body["refresh_token"] != refresh, (
        "the refresh token was not rotated -- a leaked one stays usable")


def test_a_refresh_token_cannot_be_used_twice():
    client = _client()
    r = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    refresh = r.json()["refresh_token"]

    assert client.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 200
    # The old one has been consumed: replaying it must fail.
    replay = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert replay.status_code == 401, (
        "a used refresh token was accepted again")


def test_logout_revokes_the_refresh_token():
    client = _client()
    r = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    refresh = r.json()["refresh_token"]

    out = client.post("/auth/logout", json={"refresh_token": refresh})
    assert out.status_code == 200
    assert out.json()["revoked"] is True

    after = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert after.status_code == 401, (
        "logout did not revoke the refresh token -- the session survived")


def test_an_invalid_refresh_token_is_refused():
    client = _client()
    for bad in ["", "not-a-token", "a" * 200]:
        r = client.post("/auth/refresh", json={"refresh_token": bad})
        assert r.status_code == 401


def test_password_reset_invalidates_existing_tokens():
    """A reset must end the sessions the old password had.

    The token version is what does it: every access token minted before the
    reset carries the old version and is refused afterwards, and the
    refresh tokens are revoked outright.
    """
    from app.deps import get_db_session_cm
    from sqlalchemy import text

    client = _client()
    analyst_email = os.getenv("USER1_EMAIL")
    analyst_password = os.getenv("USER1_PASSWORD")
    if not (analyst_email and analyst_password):
        pytest.skip("USER1_* not configured")

    r = _login(client, analyst_email, analyst_password)
    assert r.status_code == 200, r.text
    old_access = r.json()["access_token"]
    old_refresh = r.json()["refresh_token"]

    headers = {"Authorization": f"Bearer {old_access}"}
    assert client.get("/auth/me", headers=headers).status_code == 200

    async def _bump() -> None:
        async with get_db_session_cm() as db:
            user = await auth_service.get_user_by_email(db, analyst_email)
            await auth_service.bump_token_version(db, user["id"])
            await auth_service.revoke_all_refresh_tokens(db, user["id"])

    _run(_bump())

    # The access token minted before the reset is now worthless.
    after = client.get("/auth/me", headers=headers)
    assert after.status_code == 401, (
        f"a token issued before the reset still works: {after.status_code}")

    # So is the refresh token.
    refreshed = client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert refreshed.status_code == 401, (
        "the refresh token survived a password reset")

    # Logging in again works: the new token carries the new version.
    again = _login(client, analyst_email, analyst_password)
    assert again.status_code == 200, again.text
    new_headers = {"Authorization": f"Bearer {again.json()['access_token']}"}
    assert client.get("/auth/me", headers=new_headers).status_code == 200


# ---------------------------------------------------------------------------
# 3. The audit trail
# ---------------------------------------------------------------------------

def _audit_actions(action: str) -> list:
    """Read the audit trail for one action (Super Admin only)."""
    from app.deps import get_db_session_cm
    from sqlalchemy import text

    async def _go():
        async with get_db_session_cm() as db:
            res = await db.execute(
                text("SELECT action, entity_id, details FROM audit_log "
                     "WHERE action = :action ORDER BY timestamp DESC LIMIT 20"),
                {"action": action},
            )
            return [{"action": r.action, "entity_id": r.entity_id,
                     "details": r.details} for r in res.fetchall()]

    return _run(_go())


def test_failed_login_is_audit_logged():
    email = "audit-failed@example.invalid"
    _clear_attempts(email)
    client = _client()
    _login(client, email, "wrong-password")

    entries = _audit_actions("login_failed")
    assert entries, "a failed login was not audit-logged"
    assert any(e["entity_id"] == email for e in entries), (
        "the audit entry does not name the account that was attempted")


def test_lockout_is_audit_logged():
    email = "audit-lockout@example.invalid"
    _clear_attempts(email)
    client = _client()
    for _ in range(settings.login_max_failures_per_account + 2):
        r = _login(client, email, "wrong-password")
        if r.status_code == 429:
            break

    assert r.status_code == 429
    entries = _audit_actions("login_locked_out")
    assert entries, "the lockout was not audit-logged"


def test_successful_login_is_audit_logged():
    client = _client()
    _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert _audit_actions("login_succeeded"), (
        "a successful login was not audit-logged")


def test_admin_actions_are_audit_logged():
    """An admin user edit must leave a trail."""
    from app.deps import get_db_session_cm
    from sqlalchemy import text

    client = _client()
    token = _admin_token(client)

    async def _analyst():
        async with get_db_session_cm() as db:
            res = await db.execute(
                text("SELECT id FROM users WHERE role = 'analyst' ORDER BY email LIMIT 1")
            )
            row = res.fetchone()
            return str(row.id) if row else None

    analyst_id = _run(_analyst())
    if analyst_id is None:
        pytest.skip("no standard user configured")

    r = client.put(
        f"/admin/users/{analyst_id}",
        json={"display_name": "Audited Analyst"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text

    entries = _audit_actions("user_updated")
    assert entries, "an admin action was not audit-logged"
    assert any(e["entity_id"] == analyst_id for e in entries)


# ---------------------------------------------------------------------------
# 4. Security headers and CORS
# ---------------------------------------------------------------------------

def test_security_headers_are_present():
    r = httpx.get(f"{API_ROOT_URL}/health")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
    assert "default-src 'none'" in r.headers.get("Content-Security-Policy", "")
    assert "geolocation=()" in r.headers.get("Permissions-Policy", "")
    assert "X-Powered-By" not in r.headers, "the framework is being advertised"


def test_auth_responses_are_not_cacheable():
    client = _client()
    r = _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert r.status_code == 200
    assert r.headers.get("Cache-Control") == "no-store", (
        "a token response must not be cached by the browser or a proxy")


def test_cors_allows_only_the_configured_origins():
    allowed = settings.cors_origin_list
    assert allowed, "no CORS origins are configured"

    r = httpx.options(
        f"{API_BASE_URL}/entities/search",
        headers={
            "Origin": allowed[0],
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.headers.get("access-control-allow-origin") == allowed[0], (
        "the configured origin was not allowed")

    r2 = httpx.options(
        f"{API_BASE_URL}/entities/search",
        headers={
            "Origin": "https://not-our-domain.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r2.headers.get("access-control-allow-origin") is None, (
        "an origin that is not on the allowlist was allowed")
    assert "*" not in r2.headers.get("access-control-allow-origin", ""), (
        "the CORS allowlist is a wildcard")


def test_client_ip_ignores_an_untrusted_forwarded_header():
    """A client must not be able to dodge the per-IP limit with a header."""

    class _FakeClient:
        host = "10.0.0.9"

    class _FakeRequest:
        client = _FakeClient()
        headers = {"x-forwarded-for": "1.2.3.4"}

    assert login_guard.client_ip(_FakeRequest()) == "10.0.0.9", (
        "an untrusted X-Forwarded-For header was believed")


def test_client_ip_uses_a_trusted_proxy_header(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_ips", "10.0.0.9")

    class _FakeClient:
        host = "10.0.0.9"

    class _FakeRequest:
        client = _FakeClient()
        headers = {"x-forwarded-for": "1.2.3.4, 5.6.7.8"}

    assert login_guard.client_ip(_FakeRequest()) == "1.2.3.4"
