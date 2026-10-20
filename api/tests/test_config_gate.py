"""Tests for the production safety gates (config.py + main.py).

These lock in behaviour the deployment relies on:
  * APP_ENV=production refuses to boot with placeholder/weak secrets.
  * APP_ENV=production refuses to boot with localhost/dev CORS origins.
  * ALLOW_DEMO_SEED defaults to False and demo seeding is refused in prod.

Dev/CI behaviour (APP_ENV=development) must be unchanged.
"""

import pytest

from app.config import Settings, PLACEHOLDER_SECRETS, MIN_JWT_SECRET_LENGTH
from app import main as app_main

STRONG_JWT = "z" * (MIN_JWT_SECRET_LENGTH + 16)


def _mk(**overrides) -> Settings:
    """Build a Settings instance from explicit values, ignoring any .env file
    so the test is hermetic."""
    base = dict(
        jwt_secret=STRONG_JWT,
        neo4j_password="strong-neo4j-password",
        postgres_password="strong-postgres-password",
        cors_origins="https://app.dhanchakra.example",
        # Fixed 3-slot seeded credentials, required by the production gate.
        super_admin_email="owner@dhanchakra.example",
        super_admin_password="a" * (MIN_JWT_SECRET_LENGTH + 8),
        user1_email="analyst1@dhanchakra.example",
        user1_password="b" * (MIN_JWT_SECRET_LENGTH + 8),
        user2_email="analyst2@dhanchakra.example",
        user2_password="c" * (MIN_JWT_SECRET_LENGTH + 8),
    )
    base.update(overrides)
    return Settings(_env_file=None, **base)


# --- defaults ---------------------------------------------------------------

def test_defaults_are_safe():
    """Field defaults must be safe regardless of the ambient environment.

    We inspect the model fields rather than an instance, because
    pydantic-settings reads os.environ even with _env_file=None, so the
    container's SEED_DEMO_USERS=true would otherwise mask the default.
    """
    from pydantic_core import PydanticUndefined
    fields = Settings.model_fields

    def default_of(name):
        d = fields[name].default
        assert d is not PydanticUndefined, f"{name} has no default"
        return d

    assert default_of("app_env") == "development"
    assert default_of("allow_demo_seed") is False
    assert default_of("seed_demo_users") is False
    # And an explicit instance with values forced off still reports False.
    s = _mk(seed_demo_users=False, allow_demo_seed=False)
    assert s.allow_demo_seed is False
    assert s.seed_demo_users is False
    assert s.is_production is False


@pytest.mark.parametrize("env", ["prod", "production", "PRODUCTION", " Production "])
def test_is_production_true(env):
    assert _mk(app_env=env).is_production is True


@pytest.mark.parametrize("env", ["development", "staging", "dev", "test", ""])
def test_is_production_false(env):
    assert _mk(app_env=env).is_production is False


# --- weak secrets -----------------------------------------------------------

def test_strong_secrets_are_clean():
    assert _mk().weak_secrets == []


@pytest.mark.parametrize("placeholder", sorted(PLACEHOLDER_SECRETS))
def test_jwt_placeholders_flagged(placeholder):
    assert "JWT_SECRET" in _mk(jwt_secret=placeholder).weak_secrets


def test_short_jwt_flagged():
    assert "JWT_SECRET" in _mk(jwt_secret="short").weak_secrets


def test_jwt_exactly_at_min_length_is_ok():
    # >= MIN length is acceptable; only strictly-shorter is weak.
    assert _mk(jwt_secret="a" * MIN_JWT_SECRET_LENGTH).weak_secrets == []
    assert "JWT_SECRET" in _mk(jwt_secret="a" * (MIN_JWT_SECRET_LENGTH - 1)).weak_secrets


def test_placeholder_db_passwords_flagged():
    s = _mk(neo4j_password="change-me", postgres_password="password")
    assert set(s.weak_secrets) == {"NEO4J_PASSWORD", "POSTGRES_PASSWORD"}


# --- CORS origins -----------------------------------------------------------

@pytest.mark.parametrize("origin", [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://0.0.0.0:8080",
    "http://[::1]:5173",
])
def test_dev_origins_detected(origin):
    assert _mk(cors_origins=origin).dev_cors_origins == [origin]


def test_production_origins_are_clean():
    s = _mk(cors_origins="https://app.dhanchakra.example,https://admin.dhanchakra.example")
    assert s.dev_cors_origins == []


def test_mixed_origins_only_dev_flagged():
    s = _mk(cors_origins="https://app.dhanchakra.example,http://localhost:5173")
    assert s.dev_cors_origins == ["http://localhost:5173"]


# --- the startup gate -------------------------------------------------------

def _set_settings(monkey_target, new: Settings):
    """Point app.main's module-level settings at a test instance."""
    monkey_target.setattr(app_main, "settings", new)


def test_gate_is_noop_in_development(monkeypatch):
    # Even with terrible secrets, dev must boot (dev/CI behaviour unchanged).
    bad = _mk(app_env="development", jwt_secret="change-me",
              neo4j_password="change-me",
              cors_origins="http://localhost:5173")
    _set_settings(monkeypatch, bad)
    app_main._validate_runtime_config()  # must not raise


def test_gate_refuses_weak_secrets_in_production(monkeypatch):
    _set_settings(monkeypatch, _mk(app_env="production", jwt_secret="change-me"))
    with pytest.raises(RuntimeError) as ei:
        app_main._validate_runtime_config()
    msg = str(ei.value)
    assert "JWT_SECRET" in msg
    assert "production" in msg


def test_gate_refuses_dev_cors_in_production(monkeypatch):
    _set_settings(monkeypatch, _mk(app_env="production",
                                   cors_origins="http://localhost:5173"))
    with pytest.raises(RuntimeError) as ei:
        app_main._validate_runtime_config()
    msg = str(ei.value)
    assert "CORS_ORIGINS" in msg
    assert "localhost" in msg


def test_gate_reports_all_problems(monkeypatch):
    _set_settings(monkeypatch, _mk(
        app_env="production", jwt_secret="change-me",
        neo4j_password="password", cors_origins="http://127.0.0.1:5173"))
    with pytest.raises(RuntimeError) as ei:
        app_main._validate_runtime_config()
    msg = str(ei.value)
    assert "JWT_SECRET" in msg and "NEO4J_PASSWORD" in msg and "CORS_ORIGINS" in msg


def test_gate_allows_good_production_config(monkeypatch):
    _set_settings(monkeypatch, _mk(app_env="production"))
    app_main._validate_runtime_config()  # must not raise


# --- seeded 3-slot credential gate -----------------------------------------

def test_gate_refuses_missing_slot_credentials_in_production(monkeypatch):
    _set_settings(monkeypatch, _mk(app_env="production", user2_password=""))
    with pytest.raises(RuntimeError) as ei:
        app_main._validate_runtime_config()
    assert "USER2_PASSWORD" in str(ei.value)


def test_gate_refuses_placeholder_slot_password_in_production(monkeypatch):
    _set_settings(monkeypatch, _mk(app_env="production", super_admin_password="change-me"))
    with pytest.raises(RuntimeError) as ei:
        app_main._validate_runtime_config()
    assert "SUPER_ADMIN_PASSWORD" in str(ei.value)


def test_missing_slot_credentials_property_lists_all(monkeypatch):
    s = _mk(super_admin_email="", user1_password="changeme", user2_email="")
    problems = s.missing_slot_credentials
    assert any("SUPER_ADMIN_EMAIL" in p for p in problems)
    assert any("USER1_PASSWORD" in p for p in problems)
    assert any("USER2_EMAIL" in p for p in problems)


def test_slot_credentials_property_clean_when_all_set():
    assert _mk().missing_slot_credentials == []


def test_short_login_passwords_are_not_flagged():
    # init_env.py generates ~12-char login passwords; only placeholders and
    # missing values are rejected, not short-but-real passwords.
    s = _mk(super_admin_password="short12chars", user1_password="also12chars!",
            user2_password="third12chars")
    assert s.missing_slot_credentials == []


# --- demo seeding gate ------------------------------------------------------

def test_demo_seed_default_off():
    """The ALLOW_DEMO_SEED field default is False, and an explicit instance
    with it forced off reports False (env-independent)."""
    from pydantic_core import PydanticUndefined
    assert Settings.model_fields["allow_demo_seed"].default is False
    assert Settings.model_fields["seed_demo_users"].default is not PydanticUndefined
    assert Settings.model_fields["seed_demo_users"].default is False
    assert _mk(allow_demo_seed=False, seed_demo_users=False).allow_demo_seed is False
