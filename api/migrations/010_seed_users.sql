-- 010_seed_users.sql
-- Demo users are NO LONGER seeded here. They are created at API startup from
-- DEMO_* environment variables when SEED_DEMO_USERS=true (see app/services/auth_service.py).

-- Seed a model version entry (Backend Schema §3 model_versions)
INSERT INTO model_versions (id, version_tag, trained_on, metrics, checkpoint_path, deployed_at, is_active) VALUES
  ('b0000000-0000-4000-8000-000000000001', 'structural-v1', 'synthetic demo graph', '{"recall": 0.95, "explainable": true}', '/models/structural-v1', now(), true)
ON CONFLICT (id) DO NOTHING;
