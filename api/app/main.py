from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging

from .routes import entities
from .deps import close_connections

logger = logging.getLogger(__name__)


async def _warmup_scoring() -> None:
    """Non-blocking startup task: if a GNN checkpoint exists and the graph
    carries no gnn_v1 scores yet (fresh load/restart), score it so the
    Worklist ranks correctly without any manual step (Demo_Script setup)."""
    try:
        from .deps import get_neo4j_session
        from .services.gnn import predict as gnn_predict

        async with get_neo4j_session() as session:
            await gnn_predict.ensure_scored(session)
    except Exception as e:
        logger.warning("startup GNN warm-up skipped: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(_warmup_scoring())
    yield
    await close_connections()

app = FastAPI(
    title="Dhan-Chakra API",
    description="Graph-AI Engine for Shell Company Loops & GST Fraud Detection",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(entities.router)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "dhanchakra-api"}

@app.get("/")
async def root():
    return {
        "service": "Dhan-Chakra API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health"
    }