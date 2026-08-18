-- 008_model_versions.sql
-- Model registry — which GNN/analytics checkpoint produced which scores (Backend Schema §3)
CREATE TABLE IF NOT EXISTS model_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_tag TEXT NOT NULL,
    trained_on TEXT NOT NULL,
    metrics JSONB DEFAULT '{}',
    checkpoint_path TEXT NOT NULL,
    deployed_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT false
);
