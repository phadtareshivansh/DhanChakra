"""Demo auth: token-based login per TRD §7 (production-grade RBAC out of scope)."""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import text

SECRET_KEY = "dhanchakra-demo-secret-change-me"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str, role: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
