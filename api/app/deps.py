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
