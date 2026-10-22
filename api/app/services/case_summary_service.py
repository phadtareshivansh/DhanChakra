"""LLM case summary service for B5."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx

from ..config import settings


def build_evidence_object(case: Dict[str, Any], entity: Optional[Dict[str, Any]] = None,
                          explanation: Optional[Dict[str, Any]] = None,
                          subgraph: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build structured evidence object (only evidence, no freeform claims)."""
    ev = {
        "case": {
            "id": case.get("id"),
            "title": case.get("title"),
            "status": case.get("status"),
            "priority": case.get("priority"),
            "company_cin": case.get("company_cin"),
        },
        "entity": None,
        "cycles": [],
        "shared_directors": [],
        "shared_addresses": [],
        "eway_mismatches": [],
        "bursts": [],
        "score_drivers": [],
        "risk_score": None,
    }
    if entity:
        ev["entity"] = {
            "cin": entity.get("cin"),
            "name": entity.get("name"),
            "risk_score": entity.get("risk_score"),
            "status": entity.get("status"),
        }
        ev["risk_score"] = entity.get("risk_score")
    if explanation:
        ev["cycles"] = explanation.get("evidence", {}).get("cycles", [])
        ev["shared_directors"] = explanation.get("evidence", {}).get("shared_directors", [])
        ev["shared_addresses"] = explanation.get("evidence", {}).get("shared_addresses", [])
        ev["eway_mismatches"] = explanation.get("evidence", {}).get("eway_mismatches", [])
        ev["bursts"] = explanation.get("evidence", {}).get("bursts", [])
        ev["score_drivers"] = explanation.get("reasons", [])
    return ev


def template_summary(evidence: Dict[str, Any]) -> str:
    reasons = evidence.get("score_drivers") or []
    cycles = evidence.get("cycles") or []
    eway = evidence.get("eway_mismatches") or []
    bursts = evidence.get("bursts") or []
    parts = ["**AI-drafted, requires officer review.**"]
    if reasons:
        parts.append("Based solely on supplied evidence: " + "; ".join(reasons) + ".")
    if cycles:
        c = cycles[0]
        parts.append(f"Detected {c.get('hop_count')}-hop invoice cycle across {c.get('company_count')} entities totaling ₹{c.get('total_invoice_amount',0):,.0f}.")
    if eway:
        parts.append(f"{len(eway)} high-value invoice(s) show e-Way Bill mismatches requiring verification.")
    if bursts:
        parts.append(f"{len(bursts)} temporal burst window(s) indicate sudden volume escalation.")
    parts.append("This is a factual summary of the evidence object only; no inferences beyond listed facts are made.")
    return " ".join(parts)


async def generate_summary(evidence: Dict[str, Any]) -> Dict[str, Any]:
    if not settings.case_summary_enabled:
        return {"summary": template_summary(evidence), "evidence": evidence, "backend": "template", "flagged": "AI-drafted, requires officer review"}

    url = settings.agent_llm_url
    key = settings.agent_llm_key
    if not url or not key:
        return {"summary": template_summary(evidence), "evidence": evidence, "backend": "template", "flagged": "AI-drafted, requires officer review"}

    model = settings.case_summary_model or settings.agent_llm_model
    prompt = (
        "You are a factual case summarizer for a fraud investigation system. "
        "ONLY use the supplied JSON evidence object. Do not invent entities, amounts, dates, "
        "or conclusions. Do not claim guilt. Write 1-2 paragraphs. "
        "Label the output as 'AI-drafted, requires officer review'. "
        "Return only the summary text.\n\nEVIDENCE:\n" + json.dumps(evidence, default=str)[:settings.agent_llm_max_chars]
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1},
            )
            resp.raise_for_status()
            data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content") or ""
            if not text:
                raise ValueError("empty")
            if "AI-drafted" not in text:
                text = "**AI-drafted, requires officer review.** " + text
            return {"summary": text, "evidence": evidence, "backend": "llm", "flagged": "AI-drafted, requires officer review"}
    except Exception:
        return {"summary": template_summary(evidence), "evidence": evidence, "backend": "template_fallback", "flagged": "AI-drafted, requires officer review"}
