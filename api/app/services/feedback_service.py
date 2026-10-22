"""Analyst feedback loop service."""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text


async def add_feedback(db, user_id: Optional[str], entity_id: Optional[str],
                       entity_cin: Optional[str], label: str, note: Optional[str]) -> Dict[str, Any]:
    feedback_id = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO entity_feedback (id, entity_id, entity_cin, user_id, label, note)
        VALUES (:id, :entity_id, :entity_cin, :user_id, :label, :note)
        """),
        {"id": feedback_id, "entity_id": entity_id, "entity_cin": entity_cin,
         "user_id": user_id, "label": label, "note": note},
    )
    await db.commit()
    result = await db.execute(text("SELECT * FROM entity_feedback WHERE id = :id"), {"id": feedback_id})
    r = result.fetchone()
    return {
        "id": str(r.id),
        "entity_id": r.entity_id,
        "entity_cin": r.entity_cin,
        "user_id": str(r.user_id) if r.user_id else None,
        "label": r.label,
        "note": r.note,
        "created_at": r.created_at,
    }


async def list_feedback(db, entity_id: Optional[str] = None, entity_cin: Optional[str] = None,
                        limit: int = 100) -> List[Dict[str, Any]]:
    query = "SELECT * FROM entity_feedback WHERE 1=1"
    params = {"limit": limit}
    if entity_id:
        query += " AND entity_id = :entity_id"
        params["entity_id"] = entity_id
    if entity_cin:
        query += " AND entity_cin = :entity_cin"
        params["entity_cin"] = entity_cin
    query += " ORDER BY created_at DESC LIMIT :limit"
    result = await db.execute(text(query), params)
    out = []
    for r in result.fetchall():
        out.append({
            "id": str(r.id),
            "entity_id": r.entity_id,
            "entity_cin": r.entity_cin,
            "user_id": str(r.user_id) if r.user_id else None,
            "label": r.label,
            "note": r.note,
            "created_at": r.created_at,
        })
    return out


async def feedback_counts(db) -> Dict[str, Any]:
    result = await db.execute(text("""
    SELECT label, COUNT(*) as c
    FROM entity_feedback
    GROUP BY label
    """))
    counts = {}
    for r in result.fetchall():
        counts[r.label] = int(r.c)
    total = sum(counts.values())
    return {"counts": counts, "total": total}
