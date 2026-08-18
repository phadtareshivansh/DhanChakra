-- 009_alter_tables.sql
-- Add display_name to users (used by auth service)
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name TEXT;

-- Track which user opened a case
ALTER TABLE cases ADD COLUMN IF NOT EXISTS opened_by UUID REFERENCES users(id) ON DELETE SET NULL;
