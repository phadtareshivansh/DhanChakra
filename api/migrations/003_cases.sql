-- 003_cases.sql
CREATE TABLE cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT CHECK (status IN ('open', 'in_progress', 'closed')) DEFAULT 'open',
    assignee_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    closed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    priority SMALLINT DEFAULT 0,
    risk_score REAL DEFAULT 0.0,
    company_cin TEXT
);