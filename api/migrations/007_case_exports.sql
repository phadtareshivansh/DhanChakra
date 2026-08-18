-- 007_case_exports.sql
-- Exported evidence bundles for a case (Backend Schema §3)
CREATE TABLE IF NOT EXISTS case_exports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID REFERENCES cases(id) ON DELETE CASCADE,
    format TEXT CHECK (format IN ('json', 'pdf')) DEFAULT 'json',
    file_path TEXT,
    payload JSONB DEFAULT '{}',
    exported_by UUID REFERENCES users(id) ON DELETE SET NULL,
    exported_at TIMESTAMPTZ DEFAULT now()
);
