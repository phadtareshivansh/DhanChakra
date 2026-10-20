-- 012_user_role_limits.sql
--
-- Enforce the fixed 3-slot role model at the database level:
--   * exactly 1 admin  (Super Admin / project owner)
--   * at most 2 analysts (standard user slots)
--
-- Why a trigger for analysts: a unique index can express "at most 1" for the
-- admin, but nothing declarative expresses "at most 2". A BEFORE INSERT
-- trigger is the portable way to cap a role at an arbitrary count.
--
-- Idempotent: safe to re-run (IF NOT EXISTS / OR REPLACE / DROP TRIGGER IF
-- EXISTS). Never edit an already-applied migration; add a new one instead.

-- 1. At most one admin -------------------------------------------------------
-- Partial unique index over a constant expression: at most one row with
-- role = 'admin' may exist. Inserting a second admin raises a unique violation.
CREATE UNIQUE INDEX IF NOT EXISTS users_single_admin_idx
    ON users ((role))
    WHERE role = 'admin';

-- 2. At most two analysts ----------------------------------------------------
CREATE OR REPLACE FUNCTION enforce_analyst_cap()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    analyst_count integer;
BEGIN
    IF NEW.role = 'analyst' THEN
        SELECT count(*) INTO analyst_count
        FROM users
        WHERE role = 'analyst';
        IF analyst_count >= 2 THEN
            RAISE EXCEPTION
                'analyst_cap_reached: at most 2 analyst accounts are allowed'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS users_analyst_cap ON users;
CREATE TRIGGER users_analyst_cap
    BEFORE INSERT ON users
    FOR EACH ROW
    EXECUTE FUNCTION enforce_analyst_cap();
