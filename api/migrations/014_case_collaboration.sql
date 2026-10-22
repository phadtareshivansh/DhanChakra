-- 014_case_collaboration.sql
-- Collaboration surfaces for the redesigned case and worklist screens:
--   * case_comments      analyst discussion on a case
--   * case_activity      immutable timeline of case events
--   * case_entities      entities explicitly attached to a case
--   * entity_assignments current owner of an entity in the worklist
--   * entity_notes       free-text analyst notes on an entity
--
-- All statements are idempotent so the migration is safe to re-run on a
-- database that already has some of these tables.

CREATE TABLE IF NOT EXISTS case_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    author_id UUID REFERENCES users(id) ON DELETE SET NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_case_comments_case ON case_comments(case_id, created_at);

CREATE TABLE IF NOT EXISTS case_activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_case_activity_case ON case_activity(case_id, created_at);

CREATE TABLE IF NOT EXISTS case_entities (
    case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    entity_cin TEXT NOT NULL,
    added_by UUID REFERENCES users(id) ON DELETE SET NULL,
    added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (case_id, entity_cin)
);

CREATE INDEX IF NOT EXISTS idx_case_entities_cin ON case_entities(entity_cin);

CREATE TABLE IF NOT EXISTS entity_assignments (
    entity_cin TEXT PRIMARY KEY,
    assignee_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    assigned_by UUID REFERENCES users(id) ON DELETE SET NULL,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_entity_assignments_assignee ON entity_assignments(assignee_id);

CREATE TABLE IF NOT EXISTS entity_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_cin TEXT NOT NULL,
    author_id UUID REFERENCES users(id) ON DELETE SET NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_entity_notes_cin ON entity_notes(entity_cin, created_at);
