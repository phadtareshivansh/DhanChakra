from urllib.parse import quote_plus

from neo4j import AsyncGraphDatabase
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from contextlib import asynccontextmanager
from .config import settings

neo4j_driver = AsyncGraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password)
)

postgres_url = (
    f"postgresql+asyncpg://{quote_plus(settings.postgres_user)}:"
    f"{quote_plus(settings.postgres_password)}@"
    f"{settings.postgres_host}:{settings.postgres_port}/"
    f"{quote_plus(settings.postgres_db)}"
)

# Neon (and most managed Postgres) require TLS. Local/compose Postgres does
# not use it, so only enable it for non-local hosts unless POSTGRES_SSL says
# otherwise.
_ssl_mode = (settings.postgres_ssl or "").strip()
if not _ssl_mode and settings.postgres_host not in {
    "postgres", "localhost", "127.0.0.1", "::1",
}:
    _ssl_mode = "require"

_connect_args = {"ssl": _ssl_mode} if _ssl_mode else {}
if "-pooler" in settings.postgres_host:
    # Neon's pooled endpoint runs PgBouncer in transaction mode, which does
    # not support asyncpg's prepared-statement cache. This is an asyncpg
    # connect() argument, not a SQLAlchemy dialect argument.
    _connect_args["statement_cache_size"] = 0

_engine_kwargs = {
    "echo": False,
    # Neon suspends idle compute; a pooled connection can be dead when the
    # next request arrives. Pre-ping transparently reconnects instead of
    # failing that first query.
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "connect_args": _connect_args,
}

engine = create_async_engine(postgres_url, **_engine_kwargs)
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
    # Decode without a version first: the user has to be looked up to know
    # the current version. A token whose version no longer matches is
    # refused, which is how a password reset ends the sessions it should.
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
    if int(payload.get("tv", 1)) != int(user.get("token_version", 1)):
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token",
                    "message": "Invalid or expired token"},
        )
    return user


async def require_admin(user=Depends(get_current_user)):
    if user.get("role") != auth_service.ADMIN_ROLE:
        raise HTTPException(
            status_code=403,
            detail={"code": "forbidden", "message": "Super Admin privileges required"},
        )
    return user
