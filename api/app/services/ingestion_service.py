"""CSV ingestion: parse MCA/GST CSV uploads, load into Neo4j, and track
the job in PostgreSQL (Backend Schema §3 ingestion_jobs)."""

import csv
import io
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text


def _read_csv(content: bytes) -> List[Dict[str, str]]:
    text_content = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text_content))
    rows = [dict(r) for r in reader]
    return rows


def _normalize(row: Dict[str, str]) -> Dict[str, str]:
    return {k.strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items()}


async def ingest_mca_csv(session, rows: List[Dict[str, str]]) -> Tuple[int, int]:
    """Load company rows; returns (processed, failed)."""
    processed, failed = 0, 0
    for raw in rows:
        r = _normalize(raw)
        cin = r.get("cin") or r.get("company_cin")
        if not cin:
            failed += 1
            continue
        try:
            await session.run("""
            MERGE (c:Company {cin: $cin})
            SET c.gstin = $gstin,
                c.name = $name,
                c.incorporation_date = CASE WHEN $inc_date <> '' THEN date($inc_date) ELSE c.incorporation_date END,
                c.status = $status,
                c.authorized_capital = toFloatOrNull($auth_cap),
                c.paid_up_capital = toFloatOrNull($paid_cap),
                c.nic_code = $nic_code,
                c.roc = $roc,
                c.updated_at = datetime()
            """,
                cin=cin,
                gstin=r.get("gstin") or None,
                name=r.get("company_name") or r.get("name") or cin,
                inc_date=r.get("date_of_incorporation") or r.get("incorporation_date") or "",
                status=r.get("status") or None,
                auth_cap=r.get("authorized_capital") or r.get("auth_cap") or "",
                paid_cap=r.get("paid_up_capital") or r.get("paid_cap") or "",
                nic_code=r.get("nic_code") or None,
                roc=r.get("roc") or None,
            )
            processed += 1
        except Exception:
            failed += 1
    return processed, failed


async def ingest_gst_csv(session, rows: List[Dict[str, str]]) -> Tuple[int, int]:
    """Load transaction rows; returns (processed, failed)."""
    processed, failed = 0, 0
    for raw in rows:
        r = _normalize(raw)
        seller = r.get("gstin_seller") or r.get("seller_gstin")
        buyer = r.get("gstin_buyer") or r.get("buyer_gstin")
        amount = r.get("invoice_value") or r.get("amount")
        if not seller or not buyer or not amount:
            failed += 1
            continue
        try:
            await session.run("""
            MERGE (seller:Company {gstin: $seller})
            SET seller.name = coalesce(seller.name, $seller)
            MERGE (buyer:Company {gstin: $buyer})
            SET buyer.name = coalesce(buyer.name, $buyer)
            CREATE (t:Transaction {
                id: $id,
                invoice_no: $id,
                amount: toFloat($amount),
                date: CASE WHEN $inv_date <> '' THEN date($inv_date) ELSE date() END,
                gstin_seller: $seller,
                gstin_buyer: $buyer,
                return_period: $ret_period,
                eway_bill_ref: $eway_ref,
                created_at: datetime()
            })
            CREATE (seller)-[:BILLED]->(t)
            CREATE (t)-[:BILLED_TO]->(buyer)
            """,
                id=str(uuid.uuid4()),
                seller=seller,
                buyer=buyer,
                amount=amount,
                inv_date=r.get("invoice_date") or "",
                ret_period=r.get("return_period") or "",
                # The e-Way Bill reference the invoice cites. It is nullable:
                # a high-value invoice with no reference has no movement
                # record either, and that gap is the TASK B1 signal.
                eway_ref=r.get("eway_bill_ref") or r.get("eway_bill") or None,
            )
            processed += 1
        except Exception:
            failed += 1
    return processed, failed


async def create_ingestion_job(db, source: str, status: str = "pending") -> str:
    job_id = str(uuid.uuid4())
    await db.execute(
        text("""
        INSERT INTO ingestion_jobs (id, source, status)
        VALUES (:id, :source, :status)
        """),
        {"id": job_id, "source": source, "status": status},
    )
    await db.commit()
    return job_id


async def update_ingestion_job(db, job_id: str, status: str, processed: int = 0,
                               failed: int = 0, error_log: Optional[str] = None) -> None:
    await db.execute(
        text("""
        UPDATE ingestion_jobs
        SET status = :status,
            records_processed = :processed,
            records_failed = :failed,
            completed_at = now(),
            error_log = :error_log
        WHERE id = :id
        """),
        {"id": job_id, "status": status, "processed": processed,
         "failed": failed, "error_log": error_log},
    )
    await db.commit()


async def get_ingestion_job(db, job_id: str) -> Optional[Dict[str, Any]]:
    result = await db.execute(
        text("""
        SELECT id, source, status, started_at, completed_at,
               records_processed, records_failed, error_log
        FROM ingestion_jobs WHERE id = :id
        """),
        {"id": job_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return {
        "id": str(row.id),
        "source": row.source,
        "status": row.status,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "records_processed": row.records_processed or 0,
        "records_failed": row.records_failed or 0,
        "error_log": row.error_log,
    }
