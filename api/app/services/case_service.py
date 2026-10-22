"""Case management + case export bundles (Backend Schema §3, TRD FR10)."""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from . import audit_service


async def _row_to_case(row) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "assignee_id": str(row.assignee_id) if row.assignee_id else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "closed_at": row.closed_at,
        "metadata": row.metadata or {},
        "priority": row.priority or 0,
        "risk_score": float(row.risk_score or 0),
        "company_cin": row.company_cin,
    }


async def list_cases(db, status: Optional[str], limit: int = 100) -> List[Dict[str, Any]]:
    query = "SELECT * FROM cases"
    params = {}
    if status:
        query += " WHERE status = :status"
        params["status"] = status
    query += " ORDER BY updated_at DESC LIMIT :limit"
    params["limit"] = limit
    result = await db.execute(text(query), params)
    return [await _row_to_case(r) for r in result.fetchall()]


async def create_case(db, title: str, description: Optional[str], company_cin: Optional[str],
                      priority: int, opened_by: Optional[str]) -> Dict[str, Any]:
    case_id = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO cases (id, title, description, status, priority, company_cin, opened_by)
        VALUES (:id, :title, :description, 'open', :priority, :company_cin, :opened_by)
        """),
        {"id": case_id, "title": title, "description": description,
         "priority": priority, "company_cin": company_cin, "opened_by": opened_by},
    )
    await db.commit()
    result = await db.execute(text("SELECT * FROM cases WHERE id = :id"), {"id": case_id})
    return await _row_to_case(result.fetchone())


async def get_case(db, case_id: str) -> Optional[Dict[str, Any]]:
    result = await db.execute(text("SELECT * FROM cases WHERE id = :id"), {"id": case_id})
    row = result.fetchone()
    if not row:
        return None
    return await _row_to_case(row)


async def update_case(db, case_id: str, fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = {"title", "description", "status", "priority", "company_cin", "assignee_id", "risk_score"}
    sets = []
    params = {"id": case_id}
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k} = :{k}")
            params[k] = v
    if not sets:
        return await get_case(db, case_id)
    if fields.get("status") == "closed":
        sets.append("closed_at = now()")
    sets.append("updated_at = now()")
    await db.execute(text(f"UPDATE cases SET {', '.join(sets)} WHERE id = :id"), params)
    await db.commit()
    return await get_case(db, case_id)


async def delete_case(db, case_id: str) -> bool:
    result = await db.execute(text("DELETE FROM cases WHERE id = :id"), {"id": case_id})
    await db.commit()
    return result.rowcount > 0


async def record_export(db, case_id: str, format: str, payload: Dict[str, Any],
                        exported_by: Optional[str]) -> Dict[str, Any]:
    export_id = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO case_exports (id, case_id, format, payload, exported_by)
        VALUES (:id, :case_id, :format, :payload, :exported_by)
        """),
        {"id": export_id, "case_id": case_id, "format": format,
         "payload": json.dumps(payload, default=str), "exported_by": exported_by},
    )
    await db.commit()
    return {"id": export_id, "case_id": case_id, "format": format}


async def list_exports(db, case_id: str) -> List[Dict[str, Any]]:
    result = await db.execute(
        text("SELECT id, format, exported_at, exported_by FROM case_exports WHERE case_id = :case_id ORDER BY exported_at DESC"),
        {"case_id": case_id},
    )
    return [{"id": str(r.id), "format": r.format, "exported_at": r.exported_at,
             "exported_by": str(r.exported_by) if r.exported_by else None} for r in result.fetchall()]


async def log_audit(db, user_id: Optional[str], action: str, entity_type: Optional[str],
                    entity_id: Optional[str], details: Optional[Dict[str, Any]] = None) -> None:
    await audit_service.log_event(
        db, action, user_id=user_id, entity_type=entity_type,
        entity_id=entity_id, details=details,
    )
