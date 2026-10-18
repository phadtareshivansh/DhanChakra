"""Phase 5 unit tests: agentic PDF ingestion (TRD §4.7, Implementation Plan
Phase 5). Unit tests cover the rules extractor + confidence routing; live
tests run the endpoint flow (upload → extract → confirm → node exists) and
clean up after themselves.

Usage: docker compose exec api pytest tests -q
"""

import asyncio
import io
import os
import sys

import pytest

from app.services import agentic_ingest

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

APOLLO_TEXT = "\n".join([
    "FORM - MGT-7 / AOC-4 EXTRACT",
    "Company Name: Apollo Roadways Private Limited",
    "CIN: U60200MH2024PTC400111",
    "GSTIN: 27AADCA1234M1Z2",
    "Registered Office: 42 Goods Yard Lane, Bhiwandi, Maharashtra 421302",
    "",
    "Directors & Shareholding:",
    "Director 1: Ramesh Kulkarni, DIN: 06754321, Equity: 40%",
    "Director 2: Sunita Kulkarni, DIN: 06754322, Equity: 35%",
    "Director 3: Prakash Kulkarni, DIN: 06754323, Equity: 25%",
])


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# --- Pure-python: extractor ---

def test_extract_all_fields_high_confidence():
    ex = agentic_ingest.extract_filing(APOLLO_TEXT)
    fields = ex["fields"]
    assert ex["backend"] == "rules"
    assert fields["company_name"]["value"] == "Apollo Roadways Private Limited"
    assert fields["cin"]["value"] == "U60200MH2024PTC400111"
    assert fields["gstin"]["value"] == "27AADCA1234M1Z2"
    assert "Bhiwandi" in fields["registered_address"]["value"]
    assert fields["director_name"]["value"] == "Ramesh Kulkarni"
    assert fields["din"]["value"] == "06754321"
    assert fields["shareholding"]["value"] == "40%"
    for field, entry in fields.items():
        assert entry["confidence"] >= (0.9 if field == "din" else 0.92)


def test_extract_empty_text_yields_no_fields():
    ex = agentic_ingest.extract_filing("")
    assert ex["fields"] == {}


def test_extract_garbage_text_yields_no_fields():
    ex = agentic_ingest.extract_filing("lorem ipsum dolor sit amet" * 10)
    assert ex["fields"] == {}


def test_confidence_bounded():
    ex = agentic_ingest.extract_filing("Company Name: X\nCIN: Y\nDIN: 12345678\nDirector 1: A, Equity: 10%")
    for entry in ex["fields"].values():
        assert 0.0 <= entry["confidence"] <= 1.0


def test_llm_backend_falls_back_to_rules_without_config(monkeypatch):
    monkeypatch.setenv("AGENT_INGEST_BACKEND", "llm")
    monkeypatch.delenv("AGENT_LLM_URL", raising=False)
    monkeypatch.delenv("AGENT_LLM_KEY", raising=False)
    import importlib

    importlib.reload(agentic_ingest)
    try:
        ex = agentic_ingest.extract_filing(APOLLO_TEXT)
        assert ex["backend"] == "rules"
        assert "company_name" in ex["fields"]
    finally:
        monkeypatch.setenv("AGENT_INGEST_BACKEND", "rules")
        importlib.reload(agentic_ingest)


# --- Pure-python: review routing ---

def test_needs_review_flags_low_confidence_only():
    ex = agentic_ingest.extract_filing(APOLLO_TEXT)
    assert agentic_ingest.needs_review(ex) == []

    ex2 = {"fields": {"company_name": {"value": "X", "confidence": 0.95},
                      "din": {"value": "12345678", "confidence": 0.6}}}
    assert agentic_ingest.needs_review(ex2) == ["din"]


# --- Live: endpoint flow against the running stack ---

def test_live_document_flow():
    """Upload the generated Apollo PDF → extract → confirm → Company exists."""
    import httpx

    sys.path.insert(0, "/tmp")
    try:
        from make_sample_filings import build_pdf
    except ImportError:
        pytest.skip(
            "make_sample_filings.py unavailable; copy ingestion/scripts to /tmp "
            "(docker cp ingestion/scripts/make_sample_filings.py <api>:<container>:/tmp)"
        )

    pdf = build_pdf(APOLLO_TEXT.splitlines())

    r = httpx.post(f"{API_BASE_URL}/ingest/document",
                   files={"file": ("filing_apollo_test.pdf", pdf, "application/pdf")},
                   timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] in ("ready", "needs_review")
    assert "company_name" in body["extraction"]
    job_id = body["job_id"]

    confirmed = {k: v["value"] for k, v in body["extraction"].items()}
    rc = httpx.post(f"{API_BASE_URL}/ingest/document/confirm",
                    json={"job_id": job_id, "extraction": body["extraction"], "confirmed": confirmed},
                    timeout=60)
    assert rc.status_code == 200, rc.text
    created = rc.json()["created"]
    assert len(created["companies"]) == 1
    cid = created["companies"][0]

    from app.deps import get_neo4j_session

    async def _check():
        async with get_neo4j_session() as session:
            rec = await session.run(
                "MATCH (c:Company {id: $cid}) RETURN c.name AS name, c.source AS source, c.extraction_confidence AS conf",
                cid=cid,
            )
            data = await rec.single()
            return data

    data = _run(_check())
    assert data is not None
    assert data["name"] == "Apollo Roadways Private Limited"
    assert data["source"] == "agentic"
    assert data["conf"] >= 0.9

    async def _cleanup():
        async with get_neo4j_session() as session:
            await session.run(
                "MATCH (c:Company {id: $cid}) DETACH DELETE c "
                "WITH count(*) AS n MATCH (a:Address {source: 'agentic'}) "
                "WHERE NOT (a)<-[:REGISTERED_AT]-() DETACH DELETE a",
                cid=cid,
            )

    _run(_cleanup())


def test_live_document_bad_pdf_fails_gracefully():
    import httpx

    r = httpx.post(f"{API_BASE_URL}/ingest/document",
                   files={"file": ("garbage.pdf", b"not a pdf at all", "application/pdf")},
                   timeout=60)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert r.json()["error"]