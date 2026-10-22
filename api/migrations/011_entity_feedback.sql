-- 011_entity_feedback.sql
-- Analyst feedback loop: labels stored in Postgres, mirrored to Neo4j.

CREATE TABLE IF NOT EXISTS entity_feedback (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id TEXT,
    entity_cin TEXT,
    user_id UUID REFERENCES users(id),
    label TEXT NOT NULL CHECK (label IN ('confirm_fraud','false_positive','needs_review')),
    note TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_feedback_entity ON entity_feedback(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_feedback_cin ON entity_feedback(entity_cin);
CREATE INDEX IF NOT EXISTS idx_entity_feedback_user ON entity_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_entity_feedback_created ON entity_feedback(created_at);
