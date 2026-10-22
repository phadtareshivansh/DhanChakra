"""Watchlist and notifications service."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text


async def get_watchlist(db, user_id: str) -> List[Dict[str, Any]]:
    result = await db.execute(text("""
    SELECT w.id, w.entity_id, w.entity_cin, w.created_at
    FROM watchlist w
    WHERE w.user_id = :uid
    ORDER BY w.created_at DESC
    """), {"uid": user_id})
    return [{"id": str(r.id), "entity_id": r.entity_id, "entity_cin": r.entity_cin, "created_at": r.created_at} for r in result.fetchall()]


async def add_to_watchlist(db, user_id: str, entity_id: Optional[str], entity_cin: Optional[str]) -> Dict[str, Any]:
    await db.execute(text("""
    INSERT INTO watchlist (user_id, entity_id, entity_cin)
    VALUES (:uid, :eid, :cin)
    ON CONFLICT DO NOTHING
    """), {"uid": user_id, "eid": entity_id, "cin": entity_cin})
    await db.commit()
    return {"ok": True}


async def remove_from_watchlist(db, user_id: str, entity_id: str) -> Dict[str, Any]:
    await db.execute(text("DELETE FROM watchlist WHERE user_id = :uid AND entity_id = :eid"), {"uid": user_id, "eid": entity_id})
    await db.commit()
    return {"ok": True}


async def get_notifications(db, user_id: str, unread_only: bool = False) -> List[Dict[str, Any]]:
    q = "SELECT * FROM notifications WHERE user_id = :uid"
    if unread_only:
        q += " AND read = false"
    q += " ORDER BY created_at DESC LIMIT 100"
    result = await db.execute(text(q), {"uid": user_id})
    out = []
    for r in result.fetchall():
        out.append({"id": str(r.id), "type": r.type, "message": r.message, "entity_id": r.entity_id, "entity_cin": r.entity_cin, "read": bool(r.read), "created_at": r.created_at})
    return out


async def mark_read(db, user_id: str, notification_id: str) -> Dict[str, Any]:
    await db.execute(text("UPDATE notifications SET read = true WHERE id = :id AND user_id = :uid"), {"id": notification_id, "uid": user_id})
    await db.commit()
    return {"ok": True}


async def create_notification(db, user_id: str, ntype: str, message: str, entity_id: Optional[str] = None, entity_cin: Optional[str] = None):
    await db.execute(text("""
    INSERT INTO notifications (user_id, type, message, entity_id, entity_cin)
    VALUES (:uid, :type, :message, :eid, :cin)
    """), {"uid": user_id, "type": ntype, "message": message, "eid": entity_id, "cin": entity_cin})
    await db.commit()


async def check_watchlist_alerts(db, neo4j_session) -> int:
    # Find all watched entities and check for score crossing/bursts/cycles
    res = await db.execute(text("SELECT DISTINCT user_id, entity_id, entity_cin FROM watchlist"))
    count = 0
    for r in res.fetchall():
        try:
            q = await neo4j_session.run("MATCH (c:Company) WHERE c.id = $id OR c.cin = $cin RETURN c.risk_score AS score, c.cin AS cin, c.id AS id", id=r.entity_id, cin=r.entity_cin)
            rec = await q.single()
            if not rec:
                continue
            # Simple alert on high risk
            score = rec.get("score") or 0
            if score >= 70:
                await create_notification(db, str(r.user_id), "risk_crossed", f"Watchlist entity {rec.get('cin')} crossed high risk band (score {score})", rec.get("id"), rec.get("cin"))
                count += 1
        except Exception:
            continue
    return count
