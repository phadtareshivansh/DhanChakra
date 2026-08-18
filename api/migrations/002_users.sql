-- 002_users.sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email CITEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT CHECK (role IN ('analyst', 'admin')) DEFAULT 'analyst',
    created_at TIMESTAMPTZ DEFAULT now()
);