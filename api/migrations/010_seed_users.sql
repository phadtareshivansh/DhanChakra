-- 010_seed_users.sql
-- Demo users (TRD §7 demo auth layer). Passwords:
--   officer@dggi.gov.in / officer123
--   analyst@dggi.gov.in / analyst123
INSERT INTO users (id, email, display_name, password_hash, role) VALUES
  ('a0000000-0000-4000-8000-000000000001', 'officer@dggi.gov.in', 'Officer Sharma', '$2b$12$ygIiZ7w4ZWczYt6Du7vglu/p/Rj1fVoQx8DtAdT1EgyezIyD67rcS', 'admin'),
  ('a0000000-0000-4000-8000-000000000002', 'analyst@dggi.gov.in', 'Analyst Gupta', '$2b$12$pkY2UfTpfJTNoh6d1GaLkOkLEFfRftdzzwB0MKKS72JjW9RbBMdUq', 'analyst')
ON CONFLICT (email) DO NOTHING;

-- Seed a model version entry (Backend Schema §3 model_versions)
INSERT INTO model_versions (id, version_tag, trained_on, metrics, checkpoint_path, deployed_at, is_active) VALUES
  ('b0000000-0000-4000-8000-000000000001', 'structural-v1', 'synthetic demo graph', '{"recall": 0.95, "explainable": true}', '/models/structural-v1', now(), true)
ON CONFLICT (id) DO NOTHING;
