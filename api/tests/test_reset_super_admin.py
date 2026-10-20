"""Break-glass Super Admin recovery (scripts/reset_super_admin.py).

The script is exercised via subprocess so its real exit codes are tested, not a
re-implementation of its logic. Every test that mutates the admin row restores
the original password hash in a try/finally, so the suite stays idempotent even
when an assertion fails partway through.

Run: docker compose exec api pytest tests/test_reset_super_admin.py -q
"""

import asyncio
import os
import secrets
import subprocess
import sys

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings

SCRIPT = "/scripts/reset_super_admin.py"
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

ADMIN_EMAIL = os.getenv("SUPER_ADMIN_EMAIL")
ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD")

pytestmark = pytest.mark.skipif(
    not (ADMIN_EMAIL and ADMIN_PASSWORD),
    reason="SUPER_ADMIN_* not configured",
)


def _run_script(env_overrides, *args):
    """Run the recovery script with a controlled environment.

    A private engine/loop convention is unnecessary here: the script is a fresh
    process. We only overlay the env vars under test onto the container env.
    """
    env = dict(os.environ)
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def _db_call(coro_factory):
    """Run a DB read/write on a private engine in its own event loop.

    A fresh loop + engine per call keeps reads honest: asyncpg binds a
    connection to the loop that created it, so reusing a loop across tests
    (especially one the `event_loop` fixture has closed) can serve stale data.
    """
    async def runner():
        url = (f"postgresql+asyncpg://{settings.postgres_user}:"
               f"{settings.postgres_password}@{settings.postgres_host}:"
               f"{settings.postgres_port}/{settings.postgres_db}")
        engine = create_async_engine(url, echo=False)
        maker = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with maker() as db:
                return await coro_factory(db)
        finally:
            await engine.dispose()

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(runner())
    finally:
        loop.close()


async def _admin_row(db):
    row = (await db.execute(
        text("SELECT id, email, password_hash FROM users WHERE role = 'admin'")
    )).fetchone()
    return (str(row.id), row.email, row.password_hash) if row else None


async def _audit_count(db):
    row = (await db.execute(
        text("SELECT count(*) FROM audit_log WHERE action = 'super_admin_recovery'")
    )).scalar_one()
    return int(row)


async def _restore(db, admin_id, original_hash):
    await db.execute(
        text("UPDATE users SET password_hash = :h WHERE id = :id"),
        {"h": original_hash, "id": admin_id},
    )
    await db.commit()


def _login(email, password):
    return httpx.post(
        f"{API_BASE_URL}/auth/login", json={"email": email, "password": password}, timeout=30
    )


# --- refusal paths (no writes) ----------------------------------------------

def test_refuses_when_password_missing():
    r = _run_script({"SUPER_ADMIN_PASSWORD": ""})
    assert r.returncode == 2, r.stderr
    assert "SUPER_ADMIN_PASSWORD" in r.stderr
    # The value must never be echoed back.
    assert "change-me" not in r.stdout


def test_refuses_when_password_is_placeholder():
    r = _run_script({"SUPER_ADMIN_PASSWORD": "change-me"})
    assert r.returncode == 2, r.stderr
    assert "placeholder" in r.stderr


def test_refuses_when_email_missing():
    r = _run_script({"SUPER_ADMIN_EMAIL": ""})
    assert r.returncode == 2, r.stderr
    assert "SUPER_ADMIN_EMAIL" in r.stderr


def test_dry_run_makes_no_change_and_no_audit_row():
    admin = _db_call(_admin_row)
    assert admin, "expected an admin row to be seeded"
    _, _, before_hash = admin
    before_audits = _db_call(_audit_count)

    r = _run_script({"SUPER_ADMIN_PASSWORD": secrets.token_urlsafe(12)}, "--dry-run")
    assert r.returncode == 0, r.stderr
    assert "[dry-run]" in r.stdout

    after = _db_call(_admin_row)
    assert after[2] == before_hash, "dry-run must not change the password hash"
    assert _db_call(_audit_count) == before_audits, "dry-run must not write an audit row"


# --- happy path (restores the original hash) --------------------------------

def test_recovery_rehashes_password_and_writes_audit_row():
    admin = _db_call(_admin_row)
    assert admin, "expected an admin row to be seeded"
    admin_id, admin_email, original_hash = admin

    new_password = secrets.token_urlsafe(16)
    before_audits = _db_call(_audit_count)
    try:
        r = _run_script({"SUPER_ADMIN_PASSWORD": new_password})
        assert r.returncode == 0, r.stderr
        assert new_password not in r.stdout, "must never print the password"

        # The new password works; the previous one no longer does.
        assert _login(admin_email, new_password).status_code == 200
        old_password = os.getenv("SUPER_ADMIN_PASSWORD")
        if old_password:
            assert _login(admin_email, old_password).status_code == 401

        # Exactly one new audit row, attributed out-of-band (user_id NULL).
        assert _db_call(_audit_count) == before_audits + 1
        row = _db_call(lambda db: _latest_recovery_audit(db))
        assert row is not None
        assert row["entity_id"] == admin_id
        assert row["user_id"] is None
        assert row["details"]["via"] == "cli"
        assert row["details"]["dry_run"] is False
    finally:
        # Always put the original hash back so the suite stays idempotent.
        _db_call(lambda db: _restore(db, admin_id, original_hash))

    if os.getenv("SUPER_ADMIN_PASSWORD"):
        assert _login(admin_email, os.getenv("SUPER_ADMIN_PASSWORD")).status_code == 200


async def _latest_recovery_audit(db):
    row = (await db.execute(
        text("SELECT user_id, entity_id, details FROM audit_log "
             "WHERE action = 'super_admin_recovery' ORDER BY id DESC LIMIT 1")
    )).fetchone()
    if not row:
        return None
    return {"user_id": row.user_id, "entity_id": row.entity_id, "details": row.details}


# --- email-change guard -----------------------------------------------------

def test_email_change_refused_without_flag():
    admin = _db_call(_admin_row)
    assert admin
    admin_id, current_email, original_hash = admin
    try:
        r = _run_script({
            "SUPER_ADMIN_EMAIL": "someone-else@example.invalid",
            "SUPER_ADMIN_PASSWORD": secrets.token_urlsafe(12),
        })
        assert r.returncode == 5, r.stderr
        # Unchanged.
        assert _db_call(_admin_row)[1] == current_email
    finally:
        _db_call(lambda db: _restore(db, admin_id, original_hash))


def test_email_change_refused_when_email_taken():
    """--allow-email-change must not steal an email owned by another row."""
    admin = _db_call(_admin_row)
    assert admin
    admin_id, current_email, original_hash = admin

    taken_email = _db_call(_other_user_email)
    if taken_email is None:
        pytest.skip("no second user configured to collide with")

    try:
        r = _run_script({
            "SUPER_ADMIN_EMAIL": taken_email,
            "SUPER_ADMIN_PASSWORD": secrets.token_urlsafe(12),
        }, "--allow-email-change")
        assert r.returncode == 6, r.stderr
        assert _db_call(_admin_row)[1] == current_email
    finally:
        _db_call(lambda db: _restore(db, admin_id, original_hash))


async def _other_user_email(db):
    row = (await db.execute(
        text("SELECT email FROM users WHERE role <> 'admin' ORDER BY created_at LIMIT 1")
    )).fetchone()
    return row.email if row else None
