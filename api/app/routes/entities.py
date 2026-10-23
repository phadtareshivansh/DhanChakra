from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Header, Body, Request
from typing import Optional, List
from datetime import datetime
import uuid

from sqlalchemy import text
from ..config import settings
from ..deps import get_neo4j_session, get_db_session, get_current_user
from ..services import graph_service, ingestion_service, auth_service, case_service, feedback_service, case_summary_service, watchlist_service, login_guard, audit_service
from ..models.schemas import (
    Company, EntitySearchResponse, SearchResult, NetworkResponse, LoopResult, LoopsResponse,
    RiskJobResponse, RiskResult, Case, CaseCreate, CaseUpdate,
    IngestionJobResponse, IngestionJobStatus, User, LoginRequest, TokenResponse, RefreshRequest,
    ExplainResponse, WorklistResponse, StatsOverview, ResolveResponse, CaseExportResponse,
    ExportPreviewResponse, AuditLogEntry, GNNModelInfo, FeedbackCreate, FeedbackItem,
    AssignableUser, CaseComment, CaseCommentCreate, CaseActivityEntry, CaseEntityAdd,
    CaseEntityLink, EntityAssignmentOut, EntityNote, EntityNoteCreate,
    WorklistBulkRequest, WorklistBulkResponse, WorklistFacets,
    GraphPathsResponse, GraphTimelineResponse,
)

router = APIRouter(prefix="/api/v1", tags=["entities"])


# ---------------------------------------------------------------------------
# Auth (TRD §7 demo token layer)
# ---------------------------------------------------------------------------

# A bcrypt hash of a value nobody knows. Verifying against it when the
# address is unknown makes the response time for an unknown account the
# same as for a known one, so the endpoint cannot be used to enumerate
# accounts by how long it takes to answer.
_UNKNOWN_ACCOUNT_HASH = "$2b$12$w0ajFxjGs2H2zcQrPFxd/eWHjrtH2e9i.11j4eWaa7pkR.tYlAi2W"

_INVALID_CREDENTIALS = {
    "code": "invalid_credentials",
    "message": "Invalid email or password",
}


@router.post("/auth/login", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest, db=Depends(get_db_session)):
    """Exchange credentials for an access token and a refresh token.

    Rate limited per client IP and per account, with a temporary lockout
    after repeated failures (TASK C1). The failure message is the same
    whether the address exists or not.
    """
    ip = login_guard.client_ip(request)
    email = (body.email or "").strip().lower()

    remaining = await login_guard.lockout_seconds_remaining(db, email, ip)
    if remaining > 0:
        await audit_service.log_event(
            db, audit_service.LOGIN_LOCKED_OUT, entity_type="user",
            entity_id=email,
            details={"ip": ip, "retry_after_seconds": remaining},
        )
        raise HTTPException(
            status_code=429,
            headers={"Retry-After": str(remaining)},
            detail={"code": "too_many_attempts",
                    "message": "Too many failed attempts. Try again later."},
        )

    user = await auth_service.get_user_by_email(db, body.email)
    password_ok = auth_service.verify_password(
        body.password,
        user["password_hash"] if user else _UNKNOWN_ACCOUNT_HASH,
    )

    if not user or not password_ok:
        await login_guard.record_attempt(db, email, ip, succeeded=False)
        await audit_service.log_event(
            db, audit_service.LOGIN_FAILED, entity_type="user", entity_id=email,
            details={"ip": ip, "reason": "invalid_credentials"},
        )
        raise HTTPException(status_code=401, detail=dict(_INVALID_CREDENTIALS))

    await login_guard.record_attempt(db, email, ip, succeeded=True)
    await login_guard.clear_attempts(db, email, ip)

    token = auth_service.create_access_token(
        user["id"], user["role"], user.get("token_version", 1))
    refresh = await auth_service.issue_refresh_token(
        db, user["id"], client_ip=ip,
        user_agent=request.headers.get("user-agent"))

    await audit_service.log_event(
        db, audit_service.LOGIN_SUCCEEDED, user_id=user["id"],
        entity_type="user", entity_id=user["id"], details={"ip": ip},
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        refresh_token=refresh,
        expires_in=settings.access_token_expire_minutes * 60,
        user={
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name") or user["email"].split("@")[0],
            "role": user["role"],
        }
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, request: Request,
                  db=Depends(get_db_session)):
    """Exchange a refresh token for a new access token.

    The refresh token is single-use: presenting it revokes it and issues a
    new one. A token that was already used, revoked or expired is refused,
    so a stolen copy cannot be replayed once the real session has moved on.
    """
    user = await auth_service.consume_refresh_token(db, body.refresh_token)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_token", "message": "Invalid or expired token"},
        )

    ip = login_guard.client_ip(request)
    token = auth_service.create_access_token(
        user["id"], user["role"], user.get("token_version", 1))
    new_refresh = await auth_service.issue_refresh_token(
        db, user["id"], client_ip=ip,
        user_agent=request.headers.get("user-agent"))

    await audit_service.log_event(
        db, audit_service.TOKEN_REFRESHED, user_id=user["id"],
        entity_type="user", entity_id=user["id"], details={"ip": ip},
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        refresh_token=new_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
        user={
            "id": user["id"],
            "email": user["email"],
            "display_name": user.get("display_name") or user["email"].split("@")[0],
            "role": user["role"],
        }
    )


@router.post("/auth/logout")
async def logout(body: RefreshRequest, request: Request,
                 db=Depends(get_db_session)):
    """End the session: the refresh token is revoked server-side.

    Revoking is what makes logout mean something. The short-lived access
    token dies on its own within minutes.
    """
    ip = login_guard.client_ip(request)
    revoked = await auth_service.revoke_refresh_token(db, body.refresh_token)
    await audit_service.log_event(
        db, audit_service.LOGOUT, entity_type="user",
        entity_id=body.refresh_token[:8] if body.refresh_token else None,
        details={"ip": ip, "revoked": revoked},
    )
    return {"revoked": revoked}


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


@router.get("/entities/{entity_id}/network/timeline", response_model=GraphTimelineResponse)
async def get_entity_network_timeline(
    entity_id: str,
    hops: int = settings.default_neighborhood_hops,
    bucket: str = "month",
):
    """Invoice volume in the entity's neighbourhood, grouped by month/week."""
    if bucket not in ("month", "week"):
        raise HTTPException(status_code=422, detail={"code": "invalid_bucket", "message": "bucket must be month or week"})
    async with get_neo4j_session() as session:
        resolved = await _resolve_entity_id(session, entity_id)
        if not resolved:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Entity not found"})
        return GraphTimelineResponse(**await graph_service.get_network_timeline(session, resolved, hops, bucket))


@router.get("/graph/paths", response_model=GraphPathsResponse)
async def graph_paths(
    source: str,
    target: str,
    max_length: int = 6,
    limit: int = 5,
):
    """Shortest connecting paths between two entities.

    Accepts a graph id, CIN or GSTIN for either endpoint. Returns the union of
    the paths' nodes/edges plus a summary per path so the workspace can draw
    and rank them without a second request.
    """
    if source.strip() == target.strip():
        raise HTTPException(status_code=422, detail={"code": "same_entity", "message": "Pick two different entities"})
    async with get_neo4j_session() as session:
        source_id = await _resolve_entity_id(session, source)
        target_id = await _resolve_entity_id(session, target)
        if not source_id or not target_id:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Source or target entity not found"})
        return GraphPathsResponse(**await graph_service.find_shortest_paths(
            session, source_id, target_id, max_length, limit,
        ))


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


@router.post("/entities/{entity_id}/feedback", response_model=FeedbackItem)
async def add_entity_feedback(entity_id: str, body: FeedbackCreate, user=Depends(get_current_user),
                              db=Depends(get_db_session), neo4j=Depends(get_neo4j_session)):
    if body.label not in ("confirm_fraud", "false_positive", "needs_review"):
        raise HTTPException(status_code=422, detail={"code": "invalid_label", "message": "invalid label"})
    # resolve to cin if possible
    cin = body.entity_cin
    try:
        node = await graph_service.get_entity(neo4j, entity_id)
        if not node:
            node = await graph_service.get_entity_by_identifier(neo4j, entity_id)
        if node and not cin:
            cin = node.get("cin")
        if node:
            # mirror to Neo4j
            try:
                await neo4j.run(
                    "MATCH (c:Company {id: $id}) SET c.last_feedback = $label, c.last_feedback_at = datetime(), c.feedback_count = coalesce(c.feedback_count, 0) + 1",
                    id=node["id"], label=body.label,
                )
            except Exception:
                pass
    except Exception:
        pass
    fb = await feedback_service.add_feedback(db, user["id"], entity_id, cin, body.label, body.note)
    await case_service.log_audit(db, user["id"], "entity_feedback", "Company", entity_id, {"label": body.label})
    return fb


@router.get("/entities/{entity_id}/feedback", response_model=List[FeedbackItem])
async def list_entity_feedback(entity_id: str, db=Depends(get_db_session)):
    return await feedback_service.list_feedback(db, entity_id=entity_id)


async def _resolve_entity_cin(entity_id: str) -> tuple[Optional[str], Optional[dict]]:
    """Resolve a URL identifier (id, CIN or GSTIN) to (CIN, company node)."""
    async with get_neo4j_session() as session:
        node = await graph_service.get_entity(session, entity_id)
        if not node:
            node = await graph_service.get_entity_by_identifier(session, entity_id)
        if not node:
            return None, None
        return node.get("cin") or entity_id, node


@router.get("/entities/{entity_id}/notes", response_model=List[EntityNote])
async def list_entity_notes(entity_id: str, db=Depends(get_db_session)):
    cin, _node = await _resolve_entity_cin(entity_id)
    if not cin:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Entity not found"})
    return await case_service.list_entity_notes(db, cin)


@router.post("/entities/{entity_id}/notes", response_model=EntityNote, status_code=status.HTTP_201_CREATED)
async def add_entity_note(
    entity_id: str,
    body: EntityNoteCreate,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    cin, _node = await _resolve_entity_cin(entity_id)
    if not cin:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Entity not found"})
    note = await case_service.add_entity_note(db, cin, user["id"], body.body)
    await case_service.log_audit(db, user["id"], "entity_note", "Company", cin, {"note_id": note["id"]})
    return note


@router.get("/entities/{entity_id}/history")
async def get_entity_history(entity_id: str, db=Depends(get_db_session)):
    """Merged analyst-facing history: labels, case activity and invoices."""
    cin, node = await _resolve_entity_cin(entity_id)
    if not cin or not node:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Entity not found"})
    events = await case_service.entity_history(db, cin)
    try:
        async with get_neo4j_session() as session:
            for invoice in await graph_service.get_timeline(session, node["id"]):
                events.append({
                    "kind": "invoice",
                    "at": invoice.get("date"),
                    "title": f"Invoice to {invoice.get('counterparty', {}).get('name') or invoice.get('buyer_gstin')}",
                    "detail": f"Return period {invoice.get('return_period') or 'n/a'}",
                    "actor": None,
                    "amount": invoice.get("amount"),
                })
    except Exception:
        pass

    def _iso(value):
        return value.isoformat() if hasattr(value, "isoformat") else value

    for event in events:
        event["at"] = _iso(event.get("at"))
    events.sort(key=lambda event: str(event.get("at") or ""), reverse=True)
    return {"entity_cin": cin, "events": events}


@router.get("/feedback/stats")
async def feedback_stats(db=Depends(get_db_session)):
    return await feedback_service.feedback_counts(db)


@router.get("/watchlist")
async def get_watchlist(user=Depends(get_current_user), db=Depends(get_db_session)):
    return await watchlist_service.get_watchlist(db, user["id"])


@router.post("/watchlist")
async def add_watchlist(body: dict = Body(...), user=Depends(get_current_user), db=Depends(get_db_session)):
    return await watchlist_service.add_to_watchlist(db, user["id"], body.get("entity_id"), body.get("entity_cin"))


@router.delete("/watchlist/{entity_id}")
async def remove_watchlist(entity_id: str, user=Depends(get_current_user), db=Depends(get_db_session)):
    return await watchlist_service.remove_from_watchlist(db, user["id"], entity_id)


@router.get("/notifications")
async def get_notifications(unread_only: bool = False, user=Depends(get_current_user), db=Depends(get_db_session)):
    return await watchlist_service.get_notifications(db, user["id"], unread_only)


@router.post("/notifications/{notification_id}/read")
async def read_notification(notification_id: str, user=Depends(get_current_user), db=Depends(get_db_session)):
    return await watchlist_service.mark_read(db, user["id"], notification_id)


# ---------------------------------------------------------------------------
# Analytics (TRD §4.1-4.3)
# ---------------------------------------------------------------------------

@router.get("/health")
async def health_alias():
    """Frontend health probe (root /health also exists, but the SPA uses the
    /api/v1 base URL for everything)."""
    return {"status": "healthy", "service": "dhanchakra-api"}


@router.get("/debug/neo4j")
async def debug_neo4j():
    """Temporary deployment diagnostic: report the configured Aura identity
    and the exact connection error without exposing the password."""
    import hashlib

    password = settings.neo4j_password or ""
    clean = settings.neo4j_password_clean
    info = {
        "uri": settings.neo4j_uri,
        "user": settings.neo4j_user,
        "password_set": bool(password),
        "password_length": len(password),
        "password_length_clean": len(clean),
        "password_first_char_code": ord(password[0]) if password else None,
        "password_last_char_code": ord(password[-1]) if password else None,
        "password_sha256_prefix": hashlib.sha256(clean.encode()).hexdigest()[:12],
    }
    try:
        async with get_neo4j_session() as session:
            result = await session.run("RETURN 1 AS ok")
            record = await result.single()
            info["ok"] = bool(record and record["ok"] == 1)
    except Exception as exc:
        info["ok"] = False
        info["error"] = type(exc).__name__
        info["code"] = getattr(exc, "code", None)
        info["message"] = str(exc)[:500]
    return info


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
    has_cycles: bool = False,
    q: Optional[str] = None,
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
            session, sort, direction, state, sector, min_score, max_score, page, page_size,
            has_cycles, q,
        )
        return WorklistResponse(**data)


@router.get("/worklist/facets", response_model=WorklistFacets)
async def worklist_facets():
    """Distinct states/sectors plus the active risk-band boundaries."""
    async with get_neo4j_session() as session:
        return WorklistFacets(**await graph_service.get_worklist_facets(session))


@router.get("/worklist/assignments", response_model=List[EntityAssignmentOut])
async def worklist_assignments(cins: str = "", db=Depends(get_db_session)):
    """Current owner for a comma-separated list of CINs (one page of results)."""
    return await case_service.list_assignments(db, [c.strip() for c in cins.split(",") if c.strip()])


@router.post("/worklist/bulk", response_model=WorklistBulkResponse)
async def worklist_bulk(
    body: WorklistBulkRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Apply an action to a selection of worklist entities.

    * ``label``       queue analyst feedback for every CIN.
    * ``assign``      set the current owner of every CIN.
    * ``add_to_case`` attach every CIN to an existing case.
    """
    cins = sorted({c.strip() for c in body.entity_cins if c and c.strip()})
    if not cins:
        raise HTTPException(status_code=422, detail={"code": "invalid_selection", "message": "no entities selected"})

    if body.action == "label":
        if body.label not in ("confirm_fraud", "false_positive", "needs_review"):
            raise HTTPException(status_code=422, detail={"code": "invalid_label", "message": "invalid label"})
        affected = await case_service.bulk_label(db, cins, body.label, user["id"])
        # Mirror the label onto the graph for downstream models (best effort).
        try:
            async with get_neo4j_session() as session:
                await session.run(
                    "MATCH (c:Company) WHERE c.cin IN $cins "
                    "SET c.last_feedback = $label, c.last_feedback_at = datetime(), "
                    "c.feedback_count = coalesce(c.feedback_count, 0) + 1",
                    cins=cins, label=body.label,
                )
        except Exception:
            pass
        return WorklistBulkResponse(action=body.action, affected=affected, skipped=[])

    if body.action == "assign":
        if not body.assignee_id:
            raise HTTPException(status_code=422, detail={"code": "missing_assignee", "message": "assignee_id is required"})
        row = (await db.execute(
            text("SELECT id FROM users WHERE id = :id"), {"id": body.assignee_id}
        )).first()
        if not row:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "assignee not found"})
        affected = await case_service.bulk_assign(db, cins, body.assignee_id, user["id"])
        return WorklistBulkResponse(action=body.action, affected=affected, skipped=[])

    if body.action == "add_to_case":
        if not body.case_id:
            raise HTTPException(status_code=422, detail={"code": "missing_case", "message": "case_id is required"})
        case = await case_service.get_case(db, _valid_uuid_or_404(body.case_id))
        if not case:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
        affected = await case_service.bulk_add_to_case(db, body.case_id, cins, user["id"])
        return WorklistBulkResponse(action=body.action, affected=affected, skipped=[])

    raise HTTPException(status_code=422, detail={"code": "invalid_action", "message": "unknown action"})


@router.get("/stats/overview")
async def stats_overview(db=Depends(get_db_session)):
    async with get_neo4j_session() as session:
        from app.services.gnn import predict as gnn_predict

        await gnn_predict.ensure_scored(session)
        base = await graph_service.get_stats_overview(session, db)
        try:
            fb = await feedback_service.feedback_counts(db)
        except Exception:
            fb = {"counts": {}, "total": 0}
        base["feedback_counts"] = fb
        try:
            row = (await db.execute(text("SELECT version_tag, trained_on, deployed_at FROM model_versions WHERE is_active = true ORDER BY deployed_at DESC LIMIT 1"))).mappings().first()
            base["active_model"] = dict(row) if row else None
        except Exception:
            base["active_model"] = None
        return base


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
        db, case.title, case.description, case.company_cin, case.priority, None,
        case.assignee_id,
    )
    await case_service.log_audit(db, None, "created_case", "case", new_case["id"], {"title": case.title})
    await case_service.log_activity(
        db, new_case["id"], None, "created",
        {"title": case.title, "priority": case.priority, "company_cin": case.company_cin},
    )
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
    before = await case_service.get_case(db, _valid_uuid_or_404(case_id))
    if not before:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    changes = case.model_dump(exclude_unset=True)
    if changes.get("assignee_id") == "":
        changes["assignee_id"] = None
    updated = await case_service.update_case(db, case_id, changes)
    if not updated:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    if "status" in changes and changes["status"] != before.get("status"):
        action, detail = "status_changed", {"from": before.get("status"), "to": changes["status"]}
    elif "assignee_id" in changes and changes["assignee_id"] != before.get("assignee_id"):
        action, detail = "assigned", {"assignee_id": changes["assignee_id"]}
    else:
        action, detail = "updated", changes
    await case_service.log_activity(db, case_id, None, action, detail)
    return updated


@router.get("/cases/{case_id}/comments", response_model=List[CaseComment])
async def list_case_comments(case_id: str, db=Depends(get_db_session)):
    case = await case_service.get_case(db, _valid_uuid_or_404(case_id))
    if not case:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    return await case_service.list_comments(db, case_id)


@router.post("/cases/{case_id}/comments", response_model=CaseComment, status_code=status.HTTP_201_CREATED)
async def add_case_comment(
    case_id: str,
    body: CaseCommentCreate,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    case = await case_service.get_case(db, _valid_uuid_or_404(case_id))
    if not case:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    return await case_service.add_comment(db, case_id, user["id"], body.body)


@router.get("/cases/{case_id}/activity", response_model=List[CaseActivityEntry])
async def list_case_activity(case_id: str, db=Depends(get_db_session)):
    case = await case_service.get_case(db, _valid_uuid_or_404(case_id))
    if not case:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    return await case_service.list_activity(db, case_id)


@router.get("/cases/{case_id}/entities", response_model=List[CaseEntityLink])
async def list_case_entities(case_id: str, db=Depends(get_db_session)):
    case = await case_service.get_case(db, _valid_uuid_or_404(case_id))
    if not case:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    return await case_service.list_case_entities(db, case_id)


@router.post("/cases/{case_id}/entities", response_model=CaseEntityLink, status_code=status.HTTP_201_CREATED)
async def add_case_entity(
    case_id: str,
    body: CaseEntityAdd,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    case = await case_service.get_case(db, _valid_uuid_or_404(case_id))
    if not case:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    return await case_service.add_case_entity(db, case_id, body.entity_cin, user["id"])


@router.delete("/cases/{case_id}/entities/{entity_cin}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_case_entity(
    case_id: str,
    entity_cin: str,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    case = await case_service.get_case(db, _valid_uuid_or_404(case_id))
    if not case:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    removed = await case_service.remove_case_entity(db, case_id, entity_cin, user["id"])
    if not removed:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Entity is not attached to this case"})


@router.get("/users/assignable", response_model=List[AssignableUser])
async def list_assignable_users(
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Analysts and admins that cases/entities can be assigned to."""
    return await case_service.list_assignable_users(db)


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

    try:
        ev = case_summary_service.build_evidence_object(bundle.get("case") or case, bundle.get("entity"), bundle.get("evidence"), bundle.get("subgraph"))
        bundle["ai_summary"] = await case_summary_service.generate_summary(ev)
    except Exception:
        pass
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


@router.post("/cases/{case_id}/summary")
async def case_summary(case_id: str, db=Depends(get_db_session)):
    case = await case_service.get_case(db, _valid_uuid_or_404(case_id))
    if not case:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Case not found"})
    bundle = {}
    entity = None
    explanation = None
    subgraph = None
    if case.get("company_cin"):
        async with get_neo4j_session() as session:
            entity = await graph_service.get_entity_by_identifier(session, case["company_cin"])
            if entity:
                explanation = await graph_service.explain_entity(session, entity["id"])
                subgraph = await graph_service.get_network(session, entity["id"], settings.default_neighborhood_hops)
    evidence = case_summary_service.build_evidence_object(case, entity, explanation, subgraph)
    result = await case_summary_service.generate_summary(evidence)
    await case_service.log_audit(db, None, "generated_case_summary", "case", case_id, {"backend": result.get("backend")})
    return result


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
