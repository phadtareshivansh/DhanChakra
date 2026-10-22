-- 013_auth_hardening.sql (TASK C1)
--
-- Idempotent on purpose: this file may be applied by
-- scripts/apply_migrations.sh against a database whose schema was originally
-- created by docker-entrypoint-initdb.d, so every statement must be safe to
-- re-run.

-- Token version. Bumping it invalidates every access token already issued for
-- that user -- used when a password is reset or changed.
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 1;

-- Refresh tokens: opaque random strings, stored only as a SHA-256 hash, so a
-- database dump cannot be replayed as a login. Revocation is server-side, so
-- "log out" really ends the session.
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    issued_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    revoked_at TIMESTAMP,
    replaced_by UUID REFERENCES refresh_tokens(id) ON DELETE SET NULL,
    client_ip TEXT,
    user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at);

-- Login attempts. The rate limiter and the lockout read from here, so the
-- decision survives an API restart and can be audited after the fact.
CREATE TABLE IF NOT EXISTS login_attempts (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    client_ip TEXT NOT NULL,
    succeeded BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_login_attempts_ip ON login_attempts(client_ip, created_at);
CREATE INDEX IF NOT EXISTS idx_login_attempts_email ON login_attempts(email, created_at);

-- The applied-migration ledger, used by scripts/apply_migrations.sh so a file
-- is never applied twice. The pre-existing migrations (001-012) were applied
-- by docker-entrypoint-initdb.d before this ledger existed, so the runner
-- baselines them rather than re-running their non-idempotent DDL.
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
