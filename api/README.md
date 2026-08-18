# API Layer

FastAPI backend with endpoints for entities, analytics, ingestion, and case management.

## Structure

- `app/main.py` — FastAPI app entry point
- `app/config.py` — Settings via Pydantic
- `app/deps.py` — Neo4j and PostgreSQL connections
- `app/models/schemas.py` — Pydantic v2 models
- `app/routes/entities.py` — All API endpoints
- `tests/` — Integration tests

## Running

```bash
cd api
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Environment Variables

See `.env.example` at project root.