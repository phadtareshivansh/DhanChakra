from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging

from .config import settings
from .routes import entities
from .routes import admin as admin_routes
from .deps import close_connections

# uvicorn configures its own loggers but leaves the root logger without a
# handler at WARNING, so application loggers would be silent. Install a root
# handler so "--log-level info" style output includes our startup messages.
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")

logger = logging.getLogger(__name__)


def _validate_runtime_config() -> None:
    """Fail fast rather than boot a production instance with placeholder
    secrets, weak defaults, or localhost CORS origins.

    In development/staging this is a no-op, so dev/CI behaviour is unchanged.
    """
    if not settings.is_production:
        return

    problems: list[str] = []
    weak = settings.weak_secrets
    if weak:
        problems.append(
            "placeholder/weak secrets %s" % ", ".join(weak)
        )
    dev_origins = settings.dev_cors_origins
    if dev_origins:
        problems.append(
            "local/development CORS_ORIGINS %s" % ", ".join(dev_origins)
        )
    missing_slots = settings.missing_slot_credentials
    if missing_slots:
        problems.append(
            "seeded user slots not configured %s" % ", ".join(missing_slots)
        )

    if problems:
        raise RuntimeError(
            "Refusing to start with APP_ENV=%s: %s. "
            "Set strong values and production origins in the environment "
            "(see .env.example: JWT_SECRET, NEO4J_PASSWORD, POSTGRES_PASSWORD, "
            "CORS_ORIGINS, SUPER_ADMIN_*, USER1_*, USER2_*)."
            % (settings.app_env, "; ".join(problems))
        )


async def _seed_demo_users() -> None:
    """Non-blocking startup task: seed/refresh the fixed 3 user slots from the
    environment (no credentials baked into the code or SQL). Existing rows are
    updated in place so user IDs stay stable."""
    try:
        from .deps import get_db_session_cm
        from .services import auth_service

        async with get_db_session_cm() as db:
            await auth_service.ensure_seeded_users(db)
    except Exception as e:
        logger.warning("startup user seeding skipped: %s", e)


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
    _validate_runtime_config()
    logger.info("Dhan-Chakra API starting (APP_ENV=%s)", settings.app_env)
    asyncio.create_task(_seed_demo_users())
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
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(entities.router)
app.include_router(admin_routes.router)

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