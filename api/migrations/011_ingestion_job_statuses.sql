-- 011_ingestion_job_statuses.sql
-- Widen ingestion_jobs.status to the full set of values the application writes.
-- The original 005 constraint omitted the agentic-review flow states
-- ("ready", "needs_review") and the CSV partial-failure state
-- ("partial_success"), which made the /ingest/document and /ingest/csv
-- endpoints fail with a CHECK violation.

ALTER TABLE ingestion_jobs DROP CONSTRAINT IF EXISTS ingestion_jobs_status_check;
ALTER TABLE ingestion_jobs ADD CONSTRAINT ingestion_jobs_status_check
    CHECK (status IN ('pending', 'running', 'completed', 'failed',
                      'partial_success', 'ready', 'needs_review'));
