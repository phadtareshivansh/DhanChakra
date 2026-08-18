"""Phase 5 agentic ingestion (TRD §4.7): extract {director_name, DIN,
registered_address, shareholding} from MCA-style filing PDFs with a
per-field confidence score; low-confidence fields are routed to manual
review instead of auto-committed.

Backends (feature-flagged via AGENT_INGEST_BACKEND):
- "rules" (default): deterministic labeled-line extraction. Works offline,
  powers the live demo, confidence = pattern strength.
- "llm": optional OpenAI-compatible chat API (AGENT_LLM_URL + AGENT_LLM_KEY).
  Used only when configured; degrades to "rules" otherwise.

The module is additive: /ingest/csv and the rest of the pipeline never
depend on it (PRD NFR reliability).
"""

import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

BACKEND = os.getenv("AGENT_INGEST_BACKEND", "rules")
CONFIDENCE_THRESHOLD = float(os.getenv("AGENT_INGEST_CONFIDENCE", "0.8"))

FIELDS = ["company_name", "cin", "gstin", "registered_address", "director_name", "din", "shareholding"]


def _uid(key: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def _line_conf(line: str, pattern: str) -> float:
    """Confidence from how strongly a labeled line matches the schema."""
    if re.fullmatch(rf"{pattern}\s*:\s*.+", line):
        return 0.95
    if re.search(pattern, line, re.IGNORECASE):
        return 0.6
    return 0.0


def _extract_rules(text: str) -> Dict[str, Any]:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    out: Dict[str, Dict[str, Any]] = {}
    for field, patterns in {
        "company_name": [r"Company Name", r"LLP Name"],
        "cin": [r"CIN"],
        "gstin": [r"GSTIN"],
        "registered_address": [r"Registered Office", r"Registered Address"],
        "director_name": [r"Director \d+", r"Designated Partner[s]?\s*\d*", r"\d+\.\s"],
        "din": [r"\bDIN"],
        "shareholding": [r"\d{1,3}\s?%"],
    }.items():
        for line in lines:
            conf = max((_line_conf(line, p) for p in patterns), default=0.0)
            if conf > 0 and field not in out:
                value = line.split(":", 1)[1].strip() if ":" in line else line
                if not value:
                    continue
                out[field] = {"value": value, "confidence": round(conf, 2)}
                break

    if "din" in out:
        if re.search(r"DIN\s*:\s*\d{6,8}", out["din"]["value"]):
            out["din"]["confidence"] = max(out["din"]["confidence"], 0.9)
        m = re.search(r"\b\d{6,8}\b", out["din"]["value"])
        if m:
            out["din"]["value"] = m.group(0)

    if "director_name" in out:
        m = re.match(r"^(Director \d+|\d+\.?)\s*:\s*(.+?)(?:,|$)", out["director_name"]["value"])
        if m:
            out["director_name"]["value"] = m.group(2).strip()
            out["director_name"]["confidence"] = max(out["director_name"]["confidence"], 0.92)
        else:
            value = re.split(r",|\s*\(DIN|\s*—|\s*–", out["director_name"]["value"])[0].strip()
            value = re.sub(r"^\d+\.\s*", "", value)
            if value:
                out["director_name"]["value"] = value

    if "shareholding" in out:
        m = re.search(r"(\d{1,3})%", out["shareholding"]["value"])
        if m:
            out["shareholding"]["value"] = m.group(1) + "%"
            out["shareholding"]["confidence"] = max(out["shareholding"]["confidence"], 0.92)

    return {"fields": out, "backend": "rules"}


def _extract_llm(text: str) -> Dict[str, Any]:
    """Optional LLM backend: OpenAI-compatible chat completion returning
    strict JSON. Falls back to rules on any failure."""
    import json

    url = os.getenv("AGENT_LLM_URL")
    key = os.getenv("AGENT_LLM_KEY")
    if not url or not key:
        logger.info("AGENT_LLM_URL/KEY not set; falling back to rules backend")
        return _extract_rules(text)

    try:
        import httpx

        prompt = (
            "Extract from this MCA filing text: company_name, cin, gstin, "
            "registered_address, director_name, din, shareholding. "
            "Respond ONLY with JSON of {\"fields\": {field: {\"value\": str, "
            "\"confidence\": 0..1}}}.\n\n---\n" + text[:4000]
        )
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            json={"model": os.getenv("AGENT_LLM_MODEL", "llama-3-70b"), "messages": [{"role": "user", "content": prompt}]},
            timeout=60,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content[content.find("{"): content.rfind("}") + 1])
        return {"fields": parsed.get("fields", {}), "backend": "llm"}
    except Exception as e:
        logger.warning("LLM backend failed (%s); falling back to rules", e)
        return _extract_rules(text)


def extract_filing(text: str) -> Dict[str, Any]:
    """Run the configured backend; validate schema + confidence."""
    result = _extract_llm(text) if BACKEND == "llm" else _extract_rules(text)
    fields = result.get("fields", {})
    clean: Dict[str, Dict[str, Any]] = {}
    for f in FIELDS:
        entry = fields.get(f) or {}
        value = str(entry.get("value") or "").strip()
        if not value:
            continue
        try:
            conf = float(entry.get("confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        clean[f] = {"value": value, "confidence": round(min(max(conf, 0.0), 1.0), 2)}
    return {"fields": clean, "backend": result.get("backend", BACKEND)}


def needs_review(extraction: Dict[str, Any], threshold: float = CONFIDENCE_THRESHOLD) -> List[str]:
    return [f for f, e in extraction["fields"].items() if e["confidence"] < threshold]


async def apply_confirmed(session, extraction: Dict[str, Any], confirmed: Dict[str, str]) -> Dict[str, Any]:
    """Create Company/Director/Address nodes from the confirmed extraction,
    with confidence + source attached. Returns created entity ids."""
    if "fields" not in extraction:
        extraction = {"fields": extraction}
    fields = {k: v["value"] if isinstance(v, dict) else str(v) for k, v in extraction["fields"].items()}
    fields.update({k: v for k, v in (confirmed or {}).items() if v and v.strip()})

    company_name = fields.get("company_name")
    cin = fields.get("cin")
    gstin = fields.get("gstin")
    address = fields.get("registered_address")
    director = fields.get("director_name")
    din = fields.get("din")
    shareholding = fields.get("shareholding")

    created: Dict[str, Any] = {"companies": [], "directors": [], "addresses": []}

    if company_name or cin:
        cid = _uid("agentic:" + (cin or company_name))
        await session.run(
            """
            MERGE (c:Company {id: $cid})
            SET c.name = $name, c.cin = $cin, c.gstin = $gstin,
                c.source = 'agentic', c.extraction_confidence = $conf,
                c.updated_at = datetime()
            """,
            cid=cid, name=company_name, cin=cin or None, gstin=gstin or None,
            conf=round(max([e["confidence"] for f, e in extraction["fields"].items() if f in ("company_name", "cin")], default=0.5), 2),
        )
        created["companies"].append(cid)

        if address:
            aid = _uid("agentic_addr:" + address)
            await session.run(
                """
                MERGE (a:Address {id: $aid})
                SET a.raw_address = $address, a.normalized_address = $address,
                    a.source = 'agentic'
                WITH a
                MATCH (c:Company {id: $cid})
                MERGE (c)-[:REGISTERED_AT]->(a)
                """,
                aid=aid, address=address, cid=cid,
            )
            created["addresses"].append(aid)

        if director and din:
            did = _uid("agentic_dir:" + din)
            await session.run(
                """
                MERGE (d:Director {id: $did})
                SET d.name = $director, d.din = $din, d.source = 'agentic'
                WITH d
                MATCH (c:Company {id: $cid})
                MERGE (d)-[:DIRECTOR_OF]->(c)
                """,
                did=did, director=director, din=din, cid=cid,
            )
            created["directors"].append(did)

    return {"created": created, "shareholding": shareholding}