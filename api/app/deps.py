from neo4j import AsyncGraphDatabase
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from contextlib import asynccontextmanager
from .config import settings

neo4j_driver = AsyncGraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password)
)

postgres_url = f"postgresql+asyncpg://{settings.postgres_user}:{settings.postgres_password}@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
engine = create_async_engine(postgres_url, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@asynccontextmanager
async def get_neo4j_session():
    async with neo4j_driver.session() as session:
        yield session

@asynccontextmanager
async def get_db_session_cm():
    async with async_session_maker() as session:
        yield session

async def get_db_session():
    """FastAPI-compatible dependency: async generator yielding a DB session."""
    async with async_session_maker() as session:
        yield session

async def close_connections():
    await neo4j_driver.close()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Auth dependencies (token -> current user -> role checks)
# ---------------------------------------------------------------------------
# These wrap auth_service so routes depend on a single, testable surface.
# get_current_user: 401 when the token is missing/invalid/unknown.
# require_admin:    built on get_current_user; 403 when role != 'admin'.

from typing import Optional

from fastapi import Header, HTTPException, Depends  # noqa: E402

from .services import auth_service  # noqa: E402


async def get_current_user(
    db=Depends(get_db_session),
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthorized", "message": "Not authenticated"},
        )
    payload = auth_service.decode_token(authorization[7:])
    if not payload:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Invalid or expired token"},
        )
    user = await auth_service.get_user_by_id(db, payload.get("sub", ""))
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthorized", "message": "Unknown user"},
        )
    return user


async def require_admin(user=Depends(get_current_user)):
    if user.get("role") != auth_service.ADMIN_ROLE:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Super Admin privileges required"},
        )
    return user
