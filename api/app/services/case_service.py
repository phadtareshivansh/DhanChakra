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
                      priority: int, opened_by: Optional[str],
                      assignee_id: Optional[str] = None) -> Dict[str, Any]:
    case_id = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO cases (id, title, description, status, priority, company_cin, opened_by, assignee_id)
        VALUES (:id, :title, :description, 'open', :priority, :company_cin, :opened_by, :assignee_id)
        """),
        {"id": case_id, "title": title, "description": description,
         "priority": priority, "company_cin": company_cin, "opened_by": opened_by,
         "assignee_id": assignee_id},
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
        if k not in allowed:
            continue
        # assignee_id is the one nullable field an analyst may explicitly clear.
        if v is None and k != "assignee_id":
            continue
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


# ---------------------------------------------------------------------------
# Collaboration: comments, activity, attached entities, assignees and notes
# ---------------------------------------------------------------------------

def _author_name(row) -> Optional[str]:
    return getattr(row, "author_name", None) or getattr(row, "author_email", None)


async def log_activity(db, case_id: str, actor_id: Optional[str], action: str,
                       detail: Optional[Dict[str, Any]] = None) -> None:
    await db.execute(
        text("""
        INSERT INTO case_activity (id, case_id, actor_id, action, detail)
        VALUES (:id, :case_id, :actor_id, :action, :detail)
        """),
        {"id": str(uuid.uuid4()), "case_id": case_id, "actor_id": actor_id,
         "action": action, "detail": json.dumps(detail or {}, default=str)},
    )
    await db.commit()


async def list_comments(db, case_id: str) -> List[Dict[str, Any]]:
    result = await db.execute(
        text("""
        SELECT c.*, u.display_name AS author_name, u.email AS author_email
        FROM case_comments c
        LEFT JOIN users u ON u.id = c.author_id
        WHERE c.case_id = :case_id
        ORDER BY c.created_at ASC
        """),
        {"case_id": case_id},
    )
    return [{
        "id": str(r.id),
        "case_id": str(r.case_id),
        "author_id": str(r.author_id) if r.author_id else None,
        "author_name": _author_name(r),
        "body": r.body,
        "created_at": r.created_at,
    } for r in result.fetchall()]


async def add_comment(db, case_id: str, author_id: Optional[str], body: str) -> Dict[str, Any]:
    comment_id = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO case_comments (id, case_id, author_id, body)
        VALUES (:id, :case_id, :author_id, :body)
        """),
        {"id": comment_id, "case_id": case_id, "author_id": author_id, "body": body},
    )
    await db.commit()
    await log_activity(db, case_id, author_id, "commented", {"preview": body[:140]})
    result = await db.execute(
        text("""
        SELECT c.*, u.display_name AS author_name, u.email AS author_email
        FROM case_comments c LEFT JOIN users u ON u.id = c.author_id
        WHERE c.id = :id
        """),
        {"id": comment_id},
    )
    r = result.fetchone()
    return {
        "id": str(r.id),
        "case_id": str(r.case_id),
        "author_id": str(r.author_id) if r.author_id else None,
        "author_name": _author_name(r),
        "body": r.body,
        "created_at": r.created_at,
    }


async def list_activity(db, case_id: str, limit: int = 200) -> List[Dict[str, Any]]:
    result = await db.execute(
        text("""
        SELECT a.*, u.display_name AS author_name, u.email AS author_email
        FROM case_activity a
        LEFT JOIN users u ON u.id = a.actor_id
        WHERE a.case_id = :case_id
        ORDER BY a.created_at DESC
        LIMIT :limit
        """),
        {"case_id": case_id, "limit": limit},
    )
    out = []
    for r in result.fetchall():
        detail = r.detail
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except ValueError:
                detail = {}
        out.append({
            "id": str(r.id),
            "case_id": str(r.case_id),
            "actor_id": str(r.actor_id) if r.actor_id else None,
            "actor_name": _author_name(r),
            "action": r.action,
            "detail": detail or {},
            "created_at": r.created_at,
        })
    return out


async def list_case_entities(db, case_id: str) -> List[Dict[str, Any]]:
    result = await db.execute(
        text("""
        SELECT e.*, u.display_name AS author_name, u.email AS author_email
        FROM case_entities e
        LEFT JOIN users u ON u.id = e.added_by
        WHERE e.case_id = :case_id
        ORDER BY e.added_at ASC
        """),
        {"case_id": case_id},
    )
    return [{
        "case_id": str(r.case_id),
        "entity_cin": r.entity_cin,
        "added_by": str(r.added_by) if r.added_by else None,
        "added_at": r.added_at,
    } for r in result.fetchall()]


async def add_case_entity(db, case_id: str, entity_cin: str,
                          added_by: Optional[str]) -> Dict[str, Any]:
    await db.execute(
        text("""
        INSERT INTO case_entities (case_id, entity_cin, added_by)
        VALUES (:case_id, :entity_cin, :added_by)
        ON CONFLICT (case_id, entity_cin) DO NOTHING
        """),
        {"case_id": case_id, "entity_cin": entity_cin, "added_by": added_by},
    )
    await db.commit()
    await log_activity(db, case_id, added_by, "entity_added", {"entity_cin": entity_cin})
    result = await db.execute(
        text("SELECT * FROM case_entities WHERE case_id = :case_id AND entity_cin = :entity_cin"),
        {"case_id": case_id, "entity_cin": entity_cin},
    )
    r = result.fetchone()
    return {
        "case_id": str(r.case_id),
        "entity_cin": r.entity_cin,
        "added_by": str(r.added_by) if r.added_by else None,
        "added_at": r.added_at,
    }


async def remove_case_entity(db, case_id: str, entity_cin: str,
                             actor_id: Optional[str] = None) -> bool:
    result = await db.execute(
        text("DELETE FROM case_entities WHERE case_id = :case_id AND entity_cin = :entity_cin"),
        {"case_id": case_id, "entity_cin": entity_cin},
    )
    await db.commit()
    if result.rowcount:
        await log_activity(db, case_id, actor_id, "entity_removed", {"entity_cin": entity_cin})
        return True
    return False


async def list_assignable_users(db) -> List[Dict[str, Any]]:
    result = await db.execute(
        text("""
        SELECT id, email, display_name, role FROM users
        ORDER BY display_name NULLS LAST, email
        """)
    )
    return [{
        "id": str(r.id),
        "email": r.email,
        "display_name": r.display_name,
        "role": r.role,
    } for r in result.fetchall()]


async def list_assignments(db, cins: List[str]) -> List[Dict[str, Any]]:
    if not cins:
        return []
    placeholders = ", ".join(f":cin{i}" for i in range(len(cins)))
    params = {f"cin{i}": cin for i, cin in enumerate(cins)}
    result = await db.execute(
        text(f"""
        SELECT a.*, u.display_name AS assignee_name, u.email AS assignee_email
        FROM entity_assignments a
        LEFT JOIN users u ON u.id = a.assignee_id
        WHERE a.entity_cin IN ({placeholders})
        """),
        params,
    )
    return [{
        "entity_cin": r.entity_cin,
        "assignee_id": str(r.assignee_id) if r.assignee_id else None,
        "assignee_name": r.assignee_name or r.assignee_email,
        "assigned_at": r.assigned_at,
    } for r in result.fetchall()]


async def upsert_assignment(db, entity_cin: str, assignee_id: Optional[str],
                            assigned_by: Optional[str]) -> Optional[Dict[str, Any]]:
    if assignee_id is None:
        await db.execute(
            text("DELETE FROM entity_assignments WHERE entity_cin = :entity_cin"),
            {"entity_cin": entity_cin},
        )
        await db.commit()
        return None
    await db.execute(
        text("""
        INSERT INTO entity_assignments (entity_cin, assignee_id, assigned_by)
        VALUES (:entity_cin, :assignee_id, :assigned_by)
        ON CONFLICT (entity_cin) DO UPDATE
        SET assignee_id = EXCLUDED.assignee_id,
            assigned_by = EXCLUDED.assigned_by,
            assigned_at = now()
        """),
        {"entity_cin": entity_cin, "assignee_id": assignee_id, "assigned_by": assigned_by},
    )
    await db.commit()
    return (await list_assignments(db, [entity_cin]))[0]


async def bulk_label(db, cins: List[str], label: str,
                     user_id: Optional[str]) -> int:
    affected = 0
    for cin in cins:
        await db.execute(
            text("""
            INSERT INTO entity_feedback (entity_id, entity_cin, user_id, label, note)
            VALUES (:entity_cin, :entity_cin, :user_id, :label, 'bulk label from worklist')
            """),
            {"entity_cin": cin, "user_id": user_id, "label": label},
        )
        affected += 1
    await db.commit()
    return affected


async def bulk_assign(db, cins: List[str], assignee_id: str,
                      assigned_by: Optional[str]) -> int:
    affected = 0
    for cin in cins:
        await db.execute(
            text("""
            INSERT INTO entity_assignments (entity_cin, assignee_id, assigned_by)
            VALUES (:entity_cin, :assignee_id, :assigned_by)
            ON CONFLICT (entity_cin) DO UPDATE
            SET assignee_id = EXCLUDED.assignee_id,
                assigned_by = EXCLUDED.assigned_by,
                assigned_at = now()
            """),
            {"entity_cin": cin, "assignee_id": assignee_id, "assigned_by": assigned_by},
        )
        affected += 1
    await db.commit()
    return affected


async def bulk_add_to_case(db, case_id: str, cins: List[str],
                           added_by: Optional[str]) -> int:
    affected = 0
    for cin in cins:
        result = await db.execute(
            text("""
            INSERT INTO case_entities (case_id, entity_cin, added_by)
            VALUES (:case_id, :entity_cin, :added_by)
            ON CONFLICT (case_id, entity_cin) DO NOTHING
            """),
            {"case_id": case_id, "entity_cin": cin, "added_by": added_by},
        )
        if result.rowcount:
            affected += 1
    await db.commit()
    if affected:
        await log_activity(db, case_id, added_by, "entities_added",
                           {"count": affected, "entity_cins": cins})
    return affected


async def list_entity_notes(db, entity_cin: str) -> List[Dict[str, Any]]:
    result = await db.execute(
        text("""
        SELECT n.*, u.display_name AS author_name, u.email AS author_email
        FROM entity_notes n
        LEFT JOIN users u ON u.id = n.author_id
        WHERE n.entity_cin = :entity_cin
        ORDER BY n.created_at DESC
        """),
        {"entity_cin": entity_cin},
    )
    return [{
        "id": str(r.id),
        "entity_cin": r.entity_cin,
        "author_id": str(r.author_id) if r.author_id else None,
        "author_name": _author_name(r),
        "body": r.body,
        "created_at": r.created_at,
    } for r in result.fetchall()]


async def add_entity_note(db, entity_cin: str, author_id: Optional[str],
                          body: str) -> Dict[str, Any]:
    note_id = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO entity_notes (id, entity_cin, author_id, body)
        VALUES (:id, :entity_cin, :author_id, :body)
        """),
        {"id": note_id, "entity_cin": entity_cin, "author_id": author_id, "body": body},
    )
    await db.commit()
    result = await db.execute(
        text("""
        SELECT n.*, u.display_name AS author_name, u.email AS author_email
        FROM entity_notes n LEFT JOIN users u ON u.id = n.author_id
        WHERE n.id = :id
        """),
        {"id": note_id},
    )
    r = result.fetchone()
    return {
        "id": str(r.id),
        "entity_cin": r.entity_cin,
        "author_id": str(r.author_id) if r.author_id else None,
        "author_name": _author_name(r),
        "body": r.body,
        "created_at": r.created_at,
    }


async def entity_history(db, entity_cin: str) -> List[Dict[str, Any]]:
    """Feedback events and case activity for an entity, newest first."""
    events: List[Dict[str, Any]] = []

    feedback = await db.execute(
        text("""
        SELECT f.*, u.display_name AS author_name, u.email AS author_email
        FROM entity_feedback f
        LEFT JOIN users u ON u.id = f.user_id
        WHERE f.entity_cin = :cin OR f.entity_id = :cin
        ORDER BY f.created_at DESC
        LIMIT 100
        """),
        {"cin": entity_cin},
    )
    for r in feedback.fetchall():
        events.append({
            "kind": "feedback",
            "at": r.created_at,
            "title": f"Labelled {r.label.replace('_', ' ')}",
            "detail": r.note,
            "actor": _author_name(r),
        })

    activity = await db.execute(
        text("""
        SELECT a.*, u.display_name AS author_name, u.email AS author_email,
               c.title AS case_title, c.id AS case_id
        FROM case_activity a
        JOIN cases c ON c.id = a.case_id
        LEFT JOIN users u ON u.id = a.actor_id
        WHERE c.company_cin = :cin
           OR c.id IN (SELECT case_id FROM case_entities WHERE entity_cin = :cin)
        ORDER BY a.created_at DESC
        LIMIT 100
        """),
        {"cin": entity_cin},
    )
    for r in activity.fetchall():
        detail = r.detail
        if isinstance(detail, str):
            try:
                detail = json.loads(detail)
            except ValueError:
                detail = {}
        events.append({
            "kind": "case",
            "at": r.created_at,
            "title": f"{r.action.replace('_', ' ').capitalize()} · {r.case_title}",
            "detail": (detail or {}).get("preview"),
            "actor": _author_name(r),
        })

    notes = await db.execute(
        text("""
        SELECT n.*, u.display_name AS author_name, u.email AS author_email
        FROM entity_notes n
        LEFT JOIN users u ON u.id = n.author_id
        WHERE n.entity_cin = :cin
        ORDER BY n.created_at DESC
        LIMIT 100
        """),
        {"cin": entity_cin},
    )
    for r in notes.fetchall():
        events.append({
            "kind": "note",
            "at": r.created_at,
            "title": "Analyst note added",
            "detail": r.body,
            "actor": _author_name(r),
        })

    events.sort(key=lambda event: str(event.get("at") or ""), reverse=True)
    return events
