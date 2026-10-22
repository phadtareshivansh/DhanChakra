"""Token-based auth with the fixed 3-slot role model.

Roles are fixed: exactly one 'admin' (Super Admin / project owner) and at most
two 'analyst' (standard user) accounts. There is no self-registration; the
Super Admin manages the two standard slots. Caps are enforced both here (clean
409s) and at the DB level (migration 012_user_role_limits.sql).
"""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import text

from ..config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ADMIN_ROLE = "admin"
ANALYST_ROLE = "analyst"
MAX_ANALYSTS = 2


class UserLimitError(Exception):
    """Raised when an operation would break the fixed 3-slot role model."""


class UserExistsError(Exception):
    """Raised when an email is already taken by another user."""


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str, token_version: int = 1) -> str:
    """A short-lived bearer token.

    ``tv`` carries the user's token version. Bumping the version (on a
    password reset) makes every access token already issued for that user
    fail the check in :func:`decode_token`, so a reset really ends the
    sessions it was meant to end.
    """
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "role": role,
        "tv": int(token_version or 1),
        "typ": "access",
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_token_version: Optional[int] = None
                 ) -> Optional[Dict[str, Any]]:
    """Decode an access token, or None if it is not usable.

    ``expected_token_version`` is the version currently stored on the user.
    When it is given, a token minted before the last password reset is
    rejected.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret,
                              algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    if payload.get("typ") != "access":
        return None
    if expected_token_version is not None:
        if int(payload.get("tv", 1)) != int(expected_token_version):
            return None
    return payload


def _hash_refresh_token(token: str) -> str:
    """Refresh tokens are stored only as a SHA-256 digest.

    The token itself is a random opaque string, so a database dump cannot
    be replayed as a login.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


async def issue_refresh_token(db, user_id: str, *, client_ip: Optional[str] = None,
                              user_agent: Optional[str] = None) -> str:
    """Create a refresh token and return the opaque string to hand out."""
    token = new_refresh_token()
    expires = datetime.utcnow() + timedelta(days=settings.refresh_token_expire_days)
    await db.execute(
        text("""
        INSERT INTO refresh_tokens
            (id, user_id, token_hash, issued_at, expires_at, client_ip, user_agent)
        VALUES (:id, :user_id, :hash, now(), :expires, :ip, :ua)
        """),
        {"id": str(uuid.uuid4()), "user_id": user_id,
         "hash": _hash_refresh_token(token), "expires": expires,
         "ip": client_ip, "ua": (user_agent or "")[:255] or None},
    )
    await db.commit()
    return token


async def consume_refresh_token(db, token: str) -> Optional[Dict[str, Any]]:
    """Validate a refresh token and mark it used.

    Returns the owning user, or None when the token is unknown, expired,
    already used or revoked. A used token is revoked rather than deleted,
    so a replay is visible in the table.
    """
    if not token:
        return None
    result = await db.execute(
        text("""
        SELECT rt.id, rt.user_id, rt.expires_at, rt.revoked_at
          FROM refresh_tokens rt
         WHERE rt.token_hash = :hash
        """),
        {"hash": _hash_refresh_token(token)},
    )
    row = result.fetchone()
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at < datetime.utcnow():
        return None

    await db.execute(
        text("UPDATE refresh_tokens SET revoked_at = now() WHERE id = :id"),
        {"id": str(row.id)},
    )
    user = await get_user_by_id(db, str(row.user_id))
    if not user:
        return None
    return user


async def revoke_refresh_token(db, token: str) -> bool:
    """Revoke one refresh token (log out). Returns True if one was revoked."""
    if not token:
        return False
    result = await db.execute(
        text("""
        UPDATE refresh_tokens SET revoked_at = now()
         WHERE token_hash = :hash AND revoked_at IS NULL
        """),
        {"hash": _hash_refresh_token(token)},
    )
    await db.commit()
    return result.rowcount > 0


async def revoke_all_refresh_tokens(db, user_id: str) -> None:
    """Revoke every refresh token for a user (password reset, role change)."""
    await db.execute(
        text("""
        UPDATE refresh_tokens SET revoked_at = now()
         WHERE user_id = :user_id AND revoked_at IS NULL
        """),
        {"user_id": user_id},
    )
    await db.commit()


async def bump_token_version(db, user_id: str) -> int:
    """Invalidate every access token already issued for a user.

    Called when a password is reset or changed: the old sessions must not
    survive a credential change.
    """
    result = await db.execute(
        text("""
        UPDATE users
           SET token_version = COALESCE(token_version, 1) + 1
         WHERE id = :user_id
        RETURNING token_version
        """),
        {"user_id": user_id},
    )
    version = result.scalar_one()
    await db.commit()
    return int(version)


async def get_user_by_email(db, email: str) -> Optional[Dict[str, Any]]:
    result = await db.execute(
        text("SELECT id, email, display_name, password_hash, role, "
             "COALESCE(token_version, 1) AS token_version "
             "FROM users WHERE email = :email"),
        {"email": email},
    )
    row = result.fetchone()
    if not row:
        return None
    return {
        "id": str(row.id),
        "email": row.email,
        "display_name": row.display_name,
        "password_hash": row.password_hash,
        "role": row.role,
        "token_version": int(row.token_version or 1),
    }


async def get_user_by_id(db, user_id: str) -> Optional[Dict[str, Any]]:
    result = await db.execute(
        text("SELECT id, email, display_name, role, created_at, "
             "COALESCE(token_version, 1) AS token_version "
             "FROM users WHERE id = :id"),
        {"id": user_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return {
        "id": str(row.id),
        "email": row.email,
        "display_name": row.display_name,
        "role": row.role,
        "created_at": row.created_at,
        "token_version": int(row.token_version or 1),
    }


async def count_by_role(db, role: str) -> int:
    result = await db.execute(
        text("SELECT count(*) AS n FROM users WHERE role = :role"), {"role": role}
    )
    return int(result.scalar_one())


async def assert_can_create_role(db, role: str) -> None:
    """Service-layer mirror of the DB caps (migration 012).

    Raises UserLimitError so the API returns a clean 409 instead of a raw
    Postgres constraint error.
    """
    if role == ADMIN_ROLE:
        if await count_by_role(db, ADMIN_ROLE) >= 1:
            raise UserLimitError("Only one Super Admin account is allowed")
    elif role == ANALYST_ROLE:
        if await count_by_role(db, ANALYST_ROLE) >= MAX_ANALYSTS:
            raise UserLimitError(
                f"At most {MAX_ANALYSTS} standard user accounts are allowed"
            )


async def create_user(db, email: str, display_name: str, password: str,
                      role: str = ANALYST_ROLE) -> Dict[str, Any]:
    await assert_can_create_role(db, role)
    user_id = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO users (id, email, display_name, password_hash, role)
        VALUES (:id, :email, :display_name, :password_hash, :role)
        """),
        {"id": user_id, "email": email, "display_name": display_name,
         "password_hash": hash_password(password), "role": role},
    )
    await db.commit()
    return {"id": user_id, "email": email, "display_name": display_name, "role": role}


async def list_users(db) -> list[Dict[str, Any]]:
    """All users (Super Admin + the two slots). Never returns password_hash."""
    result = await db.execute(
        text("SELECT id, email, display_name, role, created_at "
             "FROM users ORDER BY (role = 'admin') DESC, email")
    )
    return [
        {
            "id": str(r.id),
            "email": r.email,
            "display_name": r.display_name,
            "role": r.role,
            "created_at": r.created_at,
        }
        for r in result.fetchall()
    ]


async def update_user(db, user_id: str, *, email: Optional[str] = None,
                      display_name: Optional[str] = None,
                      password: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Update a standard user's email/display_name/password.

    Role is deliberately not a parameter: the 3-slot model fixes roles, so
    PUT cannot change them. Admins cannot be edited through this path.
    """
    target = await get_user_by_id(db, user_id)
    if not target:
        return None
    if target["role"] == ADMIN_ROLE:
        raise UserLimitError("The Super Admin account cannot be modified here")

    sets, params = [], {"user_id": user_id}
    if email is not None:
        sets.append("email = :email")
        params["email"] = email
    if display_name is not None:
        sets.append("display_name = :display_name")
        params["display_name"] = display_name
    if password is not None:
        sets.append("password_hash = :password_hash")
        params["password_hash"] = hash_password(password)
    if not sets:
        return target

    await db.execute(
        text(f"UPDATE users SET {', '.join(sets)} WHERE id = :user_id"), params
    )
    if password is not None:
        # A credential change ends the sessions it was meant to end.
        await bump_token_version(db, user_id)
        await revoke_all_refresh_tokens(db, user_id)
    else:
        await db.commit()
    return await get_user_by_id(db, user_id)


async def reset_password(db, user_id: str, password: Optional[str] = None
                         ) -> Optional[str]:
    """Admin-triggered password reset for a standard user.

    Returns the new password only when one was generated (never echoes a
    caller-supplied password back).
    """
    target = await get_user_by_id(db, user_id)
    if not target:
        return None
    if target["role"] == ADMIN_ROLE:
        raise UserLimitError("The Super Admin account cannot be modified here")

    generated = None
    if not password:
        generated = secrets.token_urlsafe(12)
        password = generated
    await db.execute(
        text("UPDATE users SET password_hash = :h WHERE id = :id"),
        {"h": hash_password(password), "id": user_id},
    )
    await db.commit()
    # A reset must end every session the old password had, so the tokens
    # already issued are invalidated here rather than left working until
    # they expire.
    await bump_token_version(db, user_id)
    await revoke_all_refresh_tokens(db, user_id)
    return generated


# ---------------------------------------------------------------------------
# Fixed 3-slot seeding
# ---------------------------------------------------------------------------

def _slot_specs():
    return [
        (settings.super_admin_email, settings.super_admin_password,
         settings.super_admin_name, ADMIN_ROLE),
        (settings.user1_email, settings.user1_password,
         settings.user1_name, ANALYST_ROLE),
        (settings.user2_email, settings.user2_password,
         settings.user2_name, ANALYST_ROLE),
    ]


async def ensure_seeded_users(db) -> None:
    """Seed/refresh exactly the 3 fixed slots from the environment.

    Updates existing rows in place (by current slot occupant / role) so user
    IDs stay stable and cases.opened_by / audit_log.user_id keep pointing at
    the right account. Only inserts a row for a slot that does not exist yet.

    No credentials live in the codebase or migrations; seeding is skipped
    unless SEED_DEMO_USERS=true, and refused in production unless
    ALLOW_DEMO_SEED=true.
    """
    if not settings.seed_demo_users:
        return
    if settings.is_production and not settings.allow_demo_seed:
        logger.warning(
            "User seeding refused: APP_ENV=%s is production. "
            "Set ALLOW_DEMO_SEED=true only if this is intentional.",
            settings.app_env,
        )
        return

    created = updated = 0
    claimed: set[str] = set()  # user IDs already handled this run

    for email, password, name, role in _slot_specs():
        if not email or not password:
            logger.warning("Seeded slot (role=%s) skipped: credentials not configured", role)
            continue

        # 1. Prefer an exact email match: this slot already holds this address,
        #    so its row (and therefore its ID) is preserved.
        existing = await get_user_by_email(db, email)

        # 2. Otherwise reuse an unclaimed row of the same role, oldest first, so
        #    IDs stay stable when an admin re-points a slot to a new person.
        #    A row claimed by an earlier slot in this run is never reused: each
        #    slot maps to a distinct row.
        if existing is None or existing["id"] in claimed:
            result = await db.execute(
                text("SELECT id FROM users WHERE role = :role ORDER BY created_at, id"),
                {"role": role},
            )
            existing = None
            for row in result.fetchall():
                rid = str(row.id)
                if rid not in claimed:
                    existing = await get_user_by_id(db, rid)
                    break

        if existing and existing["id"] not in claimed:
            claimed.add(existing["id"])
            await db.execute(
                text("""
                UPDATE users
                   SET email = :email, display_name = :name, password_hash = :h
                 WHERE id = :id
                """),
                {"email": email, "name": name, "h": hash_password(password),
                 "id": existing["id"]},
            )
            updated += 1
        else:
            # No free row of this role: create the missing slot.
            await assert_can_create_role(db, role)
            new_id = str(uuid.uuid4())
            await db.execute(
                text("""
                INSERT INTO users (id, email, display_name, password_hash, role)
                VALUES (:id, :email, :display_name, :password_hash, :role)
                ON CONFLICT (email) DO NOTHING
                """),
                {"id": new_id, "email": email, "display_name": name,
                 "password_hash": hash_password(password), "role": role},
            )
            claimed.add(new_id)
            created += 1

    await db.commit()
    if created or updated:
        logger.info("Seeded users ensured: %d created, %d updated", created, updated)
