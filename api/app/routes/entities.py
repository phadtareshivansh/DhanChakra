from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Header, Body
from typing import Optional, List
from datetime import datetime
import uuid

from sqlalchemy import text
from ..config import settings
from ..deps import get_neo4j_session, get_db_session, get_current_user
from ..services import graph_service, ingestion_service, auth_service, case_service
from ..models.schemas import (
    Company, EntitySearchResponse, SearchResult, NetworkResponse, LoopResult, LoopsResponse,
    RiskJobResponse, RiskResult, Case, CaseCreate, CaseUpdate,
    IngestionJobResponse, IngestionJobStatus, User, LoginRequest, TokenResponse,
    ExplainResponse, WorklistResponse, StatsOverview, ResolveResponse, CaseExportResponse,
    ExportPreviewResponse, AuditLogEntry, GNNModelInfo
)

router = APIRouter(prefix="/api/v1", tags=["entities"])


# ---------------------------------------------------------------------------
# Auth (TRD §7 demo token layer)
# ---------------------------------------------------------------------------

@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, db=Depends(get_db_session)):
    user = await auth_service.get_user_by_email(db, body.email)
    if not user or not auth_service.verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail={"code": "invalid_credentials", "message": "Invalid email or password"})
    token = auth_service.create_access_token(user["id"], user["role"])
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name") or user["email"].split("@")[0],
            "role": user["role"],
        }
    )


@router.get("/auth/me", response_model=User)
async def me(user=Depends(get_current_user)):
    # get_current_user raises 401 when the token is missing or invalid.
    return User(id=user["id"], email=user["email"], display_name=user["display_name"], role=user["role"],
                created_at=user.get("created_at") or datetime.utcnow())


# ---------------------------------------------------------------------------
# Entities (TRD §5)
# ---------------------------------------------------------------------------

@router.get("/entities/search", response_model=EntitySearchResponse)
async def search_entities(q: str, limit: Optional[int] = None, db=Depends(get_db_session)):
    page = min(limit or settings.default_page_size, settings.max_page_size)
    async with get_neo4j_session() as session:
        results = await graph_service.search_entities(session, q, page)
        return EntitySearchResponse(results=[SearchResult(**r) for r in results], total=len(results))


async def _resolve_entity_id(session, identifier: str) -> Optional[str]:
    """Resolve a route param to a node id: accepts the graph node id, CIN, or
    GSTIN (worklist and search links carry CINs)."""
    node = await graph_service.get_entity(session, identifier)
    if not node:
        node = await graph_service.get_entity_by_identifier(session, identifier)
    return node["id"] if node else None


@router.get("/entities/{entity_id}", response_model=Company)
async def get_entity(entity_id: str, db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        from app.services.gnn import predict as gnn_predict

        await gnn_predict.ensure_scored(session)
        node = await graph_service.get_entity(session, entity_id)
        if not node:
            node = await graph_service.get_entity_by_identifier(session, entity_id)
        if not node:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Entity not found"})
        return Company(**{k: v for k, v in node.items() if k != "_labels"})


@router.get("/entities/{entity_id}/network", response_model=NetworkResponse)
async def get_entity_network(entity_id: str, hops: int = settings.default_neighborhood_hops, db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        resolved = await _resolve_entity_id(session, entity_id)
        if not resolved:
            return NetworkResponse(nodes=[], edges=[])
        return await graph_service.get_network(session, resolved, hops)


@router.get("/entities/{entity_id}/explain", response_model=ExplainResponse)
async def explain_entity(entity_id: str, db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        resolved = await _resolve_entity_id(session, entity_id)
        if not resolved:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Entity not found"})
        explanation = await graph_service.explain_entity(session, resolved)
        if not explanation:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Entity not found"})
        await case_service.log_audit(db, None, "viewed_explanation", "Company", resolved)
        return explanation


@router.get("/entities/{entity_id}/timeline")
async def get_entity_timeline(entity_id: str, db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        return {"timeline": await graph_service.get_timeline(session, entity_id)}


# ---------------------------------------------------------------------------
# Analytics (TRD §4.1-4.3)
# ---------------------------------------------------------------------------

@router.get("/health")
async def health_alias():
    """Frontend health probe (root /health also exists, but the SPA uses the
    /api/v1 base URL for everything)."""
    return {"status": "healthy", "service": "dhanchakra-api"}


@router.get("/analytics/loops", response_model=LoopsResponse)
async def get_loops(max_length: int = settings.loops_default_max_length, db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        data = await graph_service.get_loops(session, max_length)
        return LoopsResponse(loops=[LoopResult(**l) for l in data["loops"]], total=data["total"])


@router.get("/analytics/loops/{cin}", response_model=LoopsResponse)
async def get_loops_for_company(cin: str, max_length: int = settings.loops_default_max_length, db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        data = await graph_service.get_loops(session, max_length, cin=cin)
        return LoopsResponse(loops=[LoopResult(**l) for l in data["loops"]], total=data["total"])


@router.post("/analytics/wcc")
async def compute_wcc(db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        return await graph_service.compute_wcc(session)


@router.get("/analytics/centrality/{cin}")
async def get_centrality(cin: str, db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        return await graph_service.compute_centrality(session, cin)


@router.post("/analytics/structural")
async def run_structural(db=Depends(get_db_session)):
    """Materialize FraudCycle/FraudCommunity nodes, write back centrality +
    risk scores, and create RESOLVED_AS edges (Phases 1-3)."""
    async with get_neo4j_session() as session:
        summary = await graph_service.run_structural_analytics(session)
        resolution = await graph_service.run_entity_resolution(session)
        summary["entity_resolution"] = resolution
        await case_service.log_audit(db, None, "ran_structural_analytics", None, None, summary)
        return summary


@router.post("/analytics/risk", response_model=RiskJobResponse)
async def trigger_risk_scoring(db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        summary = await graph_service.trigger_risk_job(session)
        job_id = str(uuid.uuid4())
        await case_service.log_audit(db, None, "ran_risk_scoring", None, None, summary)
        return RiskJobResponse(job_id=job_id, status="completed", summary=summary)


@router.get("/analytics/risk/{job_id}", response_model=RiskResult)
async def get_risk_result(job_id: str, db=Depends(get_db_session)):
    return RiskResult(job_id=job_id, status="completed")


@router.post("/analytics/gnn/predict")
async def gnn_predict(db=Depends(get_db_session)):
    """Phase 3: run the persisted GNN checkpoint and write risk_score back
    to every company (heuristic scores are replaced with model scores)."""
    from app.services.gnn import predict as gnn

    if not gnn.is_available():
        raise HTTPException(
            status_code=503,
            detail={"code": "gnn_unavailable", "message": "GNN checkpoint not found; run python -m app.services.gnn.train"},
        )
    async with get_neo4j_session() as session:
        summary = await gnn.predict_and_writeback(session)
    await case_service.log_audit(db, None, "ran_gnn_predict", None, None, summary)
    return summary


@router.get("/analytics/gnn/model", response_model=GNNModelInfo)
async def gnn_model(db=Depends(get_db_session)):
    """Phase 3: the currently active model_versions row (which checkpoint
    produced the scores), enriched with the loaded checkpoint's runtime
    metadata (feature columns + metrics)."""
    from app.services.gnn import predict as gnn

    result = await db.execute(text("""
        SELECT id::text AS id, version_tag, trained_on, metrics, checkpoint_path,
               deployed_at, is_active
        FROM model_versions
        WHERE is_active = true
        ORDER BY deployed_at DESC
        LIMIT 1
    """))
    row = result.mappings().first()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"code": "no_active_model", "message": "No active row in model_versions"},
        )
    return {**dict(row), "checkpoint_available": gnn.is_available(), "runtime": gnn.model_meta()}


@router.post("/analytics/gnn/train")
async def gnn_train(db=Depends(get_db_session)):
    """Phase 3: pretrain on the synthetic benchmark + fine-tune on weak
    labels; persists checkpoint + registers a model_versions row."""
    from app.services.gnn import train as gnn_train_mod

    async with get_neo4j_session() as session:
        summary = await gnn_train_mod.run_pipeline(session, gnn_train_mod._default_args())
    await gnn_train_mod.register_version(db, summary)
    await case_service.log_audit(db, None, "ran_gnn_train", None, None, summary)
    return summary


# ---------------------------------------------------------------------------
# Worklist + stats (FR8, AppFlow Journey A)
# ---------------------------------------------------------------------------

@router.get("/worklist", response_model=WorklistResponse)
async def get_worklist(
    sort: str = "risk_score",
    direction: str = "desc",
    state: Optional[str] = None,
    sector: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    page: int = 1,
    page_size: Optional[int] = None,
    db=Depends(get_db_session),
):
    page = max(1, page)
    page_size = min(settings.max_page_size, max(1, page_size or settings.default_page_size))
    async with get_neo4j_session() as session:
        from app.services.gnn import predict as gnn_predict

        await gnn_predict.ensure_scored(session)
        data = await graph_service.get_worklist(
            session, sort, direction, state, sector, min_score, max_score, page, page_size
        )
        return WorklistResponse(**data)


@router.get("/stats/overview", response_model=StatsOverview)
async def stats_overview(db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        from app.services.gnn import predict as gnn_predict

        await gnn_predict.ensure_scored(session)
        return await graph_service.get_stats_overview(session, db)


# ---------------------------------------------------------------------------
# Entity resolution (Phase 2)
# ---------------------------------------------------------------------------

@router.post("/analytics/resolve", response_model=ResolveResponse)
async def run_resolution(db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        result = await graph_service.run_entity_resolution(session)
        await case_service.log_audit(db, None, "ran_entity_resolution", None, None, result)
        return ResolveResponse(**result)


# ---------------------------------------------------------------------------
# Ingestion (TRD §5, AppFlow Journey D)
# ---------------------------------------------------------------------------

@router.post("/ingest/csv", response_model=IngestionJobResponse)
async def ingest_csv(source: str = Form(...), file: UploadFile = File(...), db=Depends(get_db_session)):
    if source not in ("mca", "gst"):
        raise HTTPException(status_code=422, detail={"code": "invalid_source", "message": "source must be 'mca' or 'gst'"})
    content = await file.read()
    job_id = await ingestion_service.create_ingestion_job(db, f"{source}_csv")
    try:
        rows = ingestion_service._read_csv(content)
    except Exception as e:
        await ingestion_service.update_ingestion_job(db, job_id, "failed", 0, 0, str(e))
        return IngestionJobResponse(job_id=job_id, status="failed", source=f"{source}_csv")

    async with get_neo4j_session() as session:
        if source == "mca":
            processed, failed = await ingestion_service.ingest_mca_csv(session, rows)
        else:
            processed, failed = await ingestion_service.ingest_gst_csv(session, rows)

    status_name = "completed" if failed == 0 else ("partial_success" if processed > 0 else "failed")
    await ingestion_service.update_ingestion_job(db, job_id, status_name, processed, failed)
    await case_service.log_audit(db, None, "ran_ingestion", None, job_id,
                                 {"source": source, "processed": processed, "failed": failed})
    return IngestionJobResponse(job_id=job_id, status=status_name, source=f"{source}_csv")


@router.get("/ingest/status/{job_id}", response_model=IngestionJobStatus)
async def ingest_status(job_id: str, db=Depends(get_db_session)):
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Job not found"})
    job = await ingestion_service.get_ingestion_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Job not found"})
    return IngestionJobStatus(**job)


@router.post("/ingest/document")
async def ingest_document(file: UploadFile = File(...), db=Depends(get_db_session)):
    """Agentic PDF ingestion (Phase 5, TRD §4.7): extract filing fields with
    per-field confidence; low-confidence fields are flagged for manual
    review and NOT auto-committed."""
    content = await file.read()
    job_id = await ingestion_service.create_ingestion_job(db, "pdf")
    try:
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            raise ValueError("no extractable text in PDF")
    except Exception as e:
        await ingestion_service.update_ingestion_job(db, job_id, "failed", 0, 0, str(e))
        return {
            "job_id": job_id,
            "status": "failed",
            "source": "pdf",
            "extraction": None,
            "needs_review": [],
            "error": str(e),
        }

    from app.services import agentic_ingest

    extraction = agentic_ingest.extract_filing(text)
    review_fields = agentic_ingest.needs_review(extraction)
    if review_fields:
        status_name = "needs_review"
    else:
        status_name = "ready"
    await ingestion_service.update_ingestion_job(db, job_id, status_name, len(extraction["fields"]), 0)
    return {
        "job_id": job_id,
        "status": status_name,
        "source": "pdf",
        "backend": extraction["backend"],
        "extraction": extraction["fields"],
        "needs_review": review_fields,
        "threshold": agentic_ingest.CONFIDENCE_THRESHOLD,
    }


@router.post("/ingest/document/confirm")
async def ingest_document_confirm(
    payload: dict = Body(...), db=Depends(get_db_session)
):
    """Commit a (possibly corrected) extraction to the graph. Fields that the
    agent extracted with low confidence were surfaced in the UI for review;
    this endpoint applies the final values."""
    job_id = payload.get("job_id")
    extraction = payload.get("extraction")
    confirmed = payload.get("confirmed") or {}
    if not job_id or not extraction:
        raise HTTPException(status_code=422, detail={"code": "bad_request", "message": "job_id and extraction are required"})

    async with get_neo4j_session() as session:
        from app.services import agentic_ingest

        result = await agentic_ingest.apply_confirmed(session, extraction, confirmed)
    await ingestion_service.update_ingestion_job(db, job_id, "completed", len(extraction or {}), 0)
    await case_service.log_audit(db, None, "confirmed_agentic_ingestion", None, None, result)
    return {"job_id": job_id, "status": "completed", "created": result["created"]}


# ---------------------------------------------------------------------------
# Cases (Backend Schema §3)
# ---------------------------------------------------------------------------

@router.get("/cases", response_model=List[Case])
async def list_cases(status: Optional[str] = None, db=Depends(get_db_session)):
    return await case_service.list_cases(db, status)


@router.post("/cases", response_model=Case, status_code=status.HTTP_201_CREATED)
async def create_case(case: CaseCreate, db=Depends(get_db_session)):
    new_case = await case_service.create_case(
        db, case.title, case.description, case.company_cin, case.priority, None
    )
    await case_service.log_audit(db, None, "created_case", "case", new_case["id"], {"title": case.title})
    return new_case


def _valid_uuid_or_404(case_id: str) -> str:
    try:
        uuid.UUID(case_id)
    except ValueError:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    return case_id


@router.get("/cases/{case_id}", response_model=Case)
async def get_case(case_id: str, db=Depends(get_db_session)):
    case = await case_service.get_case(db, _valid_uuid_or_404(case_id))
    if not case:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    return case


@router.patch("/cases/{case_id}", response_model=Case)
async def update_case(case_id: str, case: CaseUpdate, db=Depends(get_db_session)):
    case = await case_service.update_case(db, _valid_uuid_or_404(case_id), case.model_dump(exclude_unset=True))
    if not case:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    return case


@router.delete("/cases/{case_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case(case_id: str, db=Depends(get_db_session)):
    deleted = await case_service.delete_case(db, _valid_uuid_or_404(case_id))
    if not deleted:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})


@router.post("/cases/{case_id}/export", response_model=CaseExportResponse)
async def export_case(case_id: str, include_network: bool = True, db=Depends(get_db_session)):
    """Export a case bundle: case metadata + entity risk + evidence + optional subgraph (FR10)."""
    case = await case_service.get_case(db, _valid_uuid_or_404(case_id))
    if not case:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})

    bundle = {
        "case": case,
        "exported_at": datetime.utcnow().isoformat(),
    }
    if case.get("company_cin"):
        async with get_neo4j_session() as session:
            entity = await graph_service.get_entity_by_identifier(session, case["company_cin"])
            if entity:
                bundle["entity"] = {k: v for k, v in entity.items() if k != "_labels"}
                explanation = await graph_service.explain_entity(session, entity["id"])
                bundle["evidence"] = explanation
                if include_network:
                    bundle["subgraph"] = await graph_service.get_network(
                        session, entity["id"], settings.default_neighborhood_hops)

    result = await case_service.record_export(db, case_id, "json", bundle, None)
    await case_service.log_audit(db, None, "exported_case", "case", case_id,
                                 {"export_id": result["id"], "format": "json"})
    return CaseExportResponse(export_id=result["id"], format="json", payload=bundle)


@router.get("/cases/{case_id}/export/preview", response_model=ExportPreviewResponse)
async def preview_export(case_id: str, db=Depends(get_db_session)):
    """Light-mode print-ready preview bundle (AppFlow /case/:id/export)."""
    case = await case_service.get_case(db, _valid_uuid_or_404(case_id))
    if not case:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    bundle = {"case": case, "exported_at": datetime.utcnow().isoformat()}
    if case.get("company_cin"):
        async with get_neo4j_session() as session:
            entity = await graph_service.get_entity_by_identifier(session, case["company_cin"])
            if entity:
                bundle["entity"] = {k: v for k, v in entity.items() if k != "_labels"}
                bundle["evidence"] = await graph_service.explain_entity(session, entity["id"])
                bundle["subgraph"] = await graph_service.get_network(
                    session, entity["id"], settings.default_neighborhood_hops)
    return ExportPreviewResponse(payload=bundle)


@router.get("/cases/{case_id}/exports", response_model=List[dict])
async def list_case_exports(case_id: str, db=Depends(get_db_session)):
    return await case_service.list_exports(db, _valid_uuid_or_404(case_id))


# ---------------------------------------------------------------------------
# Audit log (Backend Schema §3)
# ---------------------------------------------------------------------------

@router.get("/audit", response_model=List[AuditLogEntry])
async def list_audit(limit: Optional[int] = None, db=Depends(get_db_session)):
    page = min(limit or settings.audit_log_max_limit, settings.audit_log_max_limit)
    result = await db.execute(
        text("SELECT id, user_id, action, entity_type, entity_id, details, timestamp FROM audit_log ORDER BY timestamp DESC LIMIT :limit"),
        {"limit": page},
    )
    entries = []
    for r in result.fetchall():
        entries.append(AuditLogEntry(
            id=str(r.id),
            user_id=str(r.user_id) if r.user_id else None,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            details=r.details or {},
            timestamp=r.timestamp,
        ))
    return entries
