"""Demo auth: token-based login per TRD §7 (production-grade RBAC out of scope)."""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import text

from ..config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None


async def get_user_by_email(db, email: str) -> Optional[Dict[str, Any]]:
    result = await db.execute(
        text("SELECT id, email, display_name, password_hash, role FROM users WHERE email = :email"),
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
    }


async def get_user_by_id(db, user_id: str) -> Optional[Dict[str, Any]]:
    result = await db.execute(
        text("SELECT id, email, display_name, role FROM users WHERE id = :id"),
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
    }


async def create_user(db, email: str, display_name: str, password: str, role: str = "analyst") -> Dict[str, Any]:
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


async def ensure_demo_users(db) -> None:
    """Idempotently seed demo users from DEMO_* environment settings.

    No credentials live in the codebase or migrations: seeding only happens
    when SEED_DEMO_USERS=true and the corresponding DEMO_* variables are set.
    Seeding is additionally refused in production unless ALLOW_DEMO_SEED=true.
    """
    if not settings.seed_demo_users:
        return
    if settings.is_production and not settings.allow_demo_seed:
        logger.warning(
            "Demo-user seeding refused: APP_ENV=%s is production. "
            "Set ALLOW_DEMO_SEED=true only if this is intentional.",
            settings.app_env,
        )
        return

    demos = [
        (settings.demo_admin_email, settings.demo_admin_password,
         settings.demo_admin_name, "admin"),
        (settings.demo_analyst_email, settings.demo_analyst_password,
         settings.demo_analyst_name, "analyst"),
    ]
    created = 0
    for email, password, name, role in demos:
        if not email or not password:
            logger.warning("Demo user (role=%s) skipped: DEMO_* credentials not configured", role)
            continue
        await db.execute(
            text("""
            INSERT INTO users (id, email, display_name, password_hash, role)
            VALUES (:id, :email, :display_name, :password_hash, :role)
            ON CONFLICT (email) DO NOTHING
            """),
            {"id": str(uuid.uuid4()), "email": email, "display_name": name,
             "password_hash": hash_password(password), "role": role},
        )
        created += 1
    await db.commit()
    if created:
        logger.info("Demo users ensured: %d", created)
