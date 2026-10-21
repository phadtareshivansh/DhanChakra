from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# Values that obviously are not real secrets. Used by the production gate so a
# deployment cannot silently boot with the placeholders from .env.example.
PLACEHOLDER_SECRETS = frozenset({
    "", "change-me", "changeme", "change_me", "change-this", "changethis",
    "secret", "password", "dev", "dev-secret", "test", "example",
})
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    """Application settings. Non-secret operational defaults are provided;
    credentials and secrets MUST come from the environment (no defaults)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Neo4j ---
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str

    # --- PostgreSQL ---
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "dhanchakra"
    postgres_password: str
    postgres_db: str = "dhanchakra"

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    # Comma-separated browser origins allowed to call the API. Override with
    # the CORS_ORIGINS environment variable; production refuses to start if
    # any origin is a local/dev origin (see dev_cors_origins).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_page_size: int = 100
    default_page_size: int = 20

    # --- Deployment ---
    # "development" | "staging" | "production". Production turns on the safety
    # gates below: placeholder secrets refuse to boot and demo seeding is off
    # unless explicitly allowed with ALLOW_DEMO_SEED=true.
    app_env: str = "development"
    allow_demo_seed: bool = False

    # --- Auth ---
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # --- Seeded user slots (fixed 3-slot model) ---
    # Exactly one Super Admin (role 'admin') and two standard users (role
    # 'analyst'). No credentials live in code or migrations: these come from
    # the environment and the rows are seeded/updated at API startup.
    seed_demo_users: bool = False
    super_admin_email: Optional[str] = None
    super_admin_password: Optional[str] = None
    super_admin_name: str = "Super Admin"
    user1_email: Optional[str] = None
    user1_password: Optional[str] = None
    user1_name: str = "Analyst One"
    user2_email: Optional[str] = None
    user2_password: Optional[str] = None
    user2_name: str = "Analyst Two"

    # --- Heuristic risk scoring (all weights configurable) ---
    risk_cycle_base: float = 40
    risk_cycle_step: float = 5
    risk_cycle_cap: float = 20
    risk_director_weight: float = 5
    risk_director_cap: float = 15
    risk_address_weight: float = 4
    risk_address_cap: float = 10
    risk_degree_weight: float = 2
    risk_degree_cap: float = 10
    risk_pagerank_weight: float = 150
    risk_pagerank_cap: float = 15
    risk_betweenness_weight: float = 100
    risk_betweenness_cap: float = 10
    risk_flag_threshold: float = 40
    eway_high_value_threshold: float = 50000.0
    burst_window_days: int = 7
    burst_z_threshold: float = 2.0
    burst_min_transactions: int = 3
    # Minimum distinct counterparties before the degree term contributes
    risk_degree_min: int = 2
    # Heuristic score is clamped to this maximum
    risk_score_cap: float = 100.0

    # --- Graph analytics ---
    max_cycle_hops: int = 8
    min_cycle_length: int = 3
    max_neighborhood_hops: int = 5
    default_neighborhood_hops: int = 2
    loops_default_max_length: int = 6
    weak_label_threshold: float = 40
    entity_resolution_fuzzy_threshold: float = 0.92
    # Jaro-Winkler internals: longest common prefix considered and its weight
    entity_resolution_prefix_max: int = 4
    entity_resolution_prefix_scale: float = 0.1

    # --- Query result guards (defensive caps on path-enumeration queries) ---
    max_ring_paths: int = 50
    max_entity_loop_paths: int = 50
    max_global_loop_paths: int = 100
    max_cycle_paths: int = 1000
    audit_log_max_limit: int = 100

    # --- GDS (Neo4j Graph Data Science) ---
    gds_projection_name: str = "company_invoice_graph"
    gds_louvain_max_iterations: int = 20

    # --- GNN training defaults ---
    gnn_default_epochs: int = 60
    gnn_finetune_epochs: int = 120
    gnn_benchmark_graphs: int = 40
    gnn_decision_threshold: float = 0.5
    gnn_checkpoint_dir: str = "/app/models"
    gnn_checkpoint_filename: str = "gnn_risk_v1.pt"
    gnn_metrics_filename: str = "gnn_metrics.json"
    gnn_checkpoint_path: Optional[str] = None  # overrides dir/filename when set

    # --- Agentic ingestion (MCA filing extraction) ---
    agent_ingest_backend: str = "rules"
    agent_ingest_confidence: float = 0.8
    agent_llm_max_chars: int = 4000
    agent_llm_url: Optional[str] = None
    agent_llm_key: Optional[str] = None
    agent_llm_model: str = "llama-3-70b"

    @property
    def gnn_checkpoint_file(self) -> str:
        import os

        if self.gnn_checkpoint_path:
            return self.gnn_checkpoint_path
        return os.path.join(self.gnn_checkpoint_dir, self.gnn_checkpoint_filename)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"prod", "production"}

    @property
    def weak_secrets(self) -> list[str]:
        """Names of secret settings still set to a placeholder/weak value.

        Used by the production startup gate; empty in a sane deployment.
        """
        weak: list[str] = []
        jwt_secret = self.jwt_secret.strip()
        if (jwt_secret.lower() in PLACEHOLDER_SECRETS
                or len(jwt_secret) < MIN_JWT_SECRET_LENGTH):
            weak.append("JWT_SECRET")
        for name, value in (("NEO4J_PASSWORD", self.neo4j_password),
                            ("POSTGRES_PASSWORD", self.postgres_password)):
            if value.strip().lower() in PLACEHOLDER_SECRETS:
                weak.append(name)
        return weak

    @property
    def dev_cors_origins(self) -> list[str]:
        """Allowed origins that are only appropriate for local development.

        A production boot must not serve CORS for these; the startup gate
        refuses to start if any are present (see _validate_runtime_config).
        """
        dev_markers = ("localhost", "127.0.0.1", "0.0.0.0", "::1")
        return [o for o in self.cors_origin_list
                if any(m in o.lower() for m in dev_markers)]

    @property
    def missing_slot_credentials(self) -> list[str]:
        """Names of seeded-slot env vars that are absent or still placeholders.

        The fixed 3-slot model (1 Super Admin + 2 analysts) cannot be seeded
        without these. Production refuses to boot if any are missing or weak,
        mirroring the weak-secrets gate.
        """
        problems: list[str] = []
        slots = (
            ("SUPER_ADMIN_EMAIL", self.super_admin_email),
            ("SUPER_ADMIN_PASSWORD", self.super_admin_password),
            ("USER1_EMAIL", self.user1_email),
            ("USER1_PASSWORD", self.user1_password),
            ("USER2_EMAIL", self.user2_email),
            ("USER2_PASSWORD", self.user2_password),
        )
        for name, value in slots:
            v = (value or "").strip()
            if not v:
                problems.append(f"{name} (missing)")
            elif name.endswith("_PASSWORD") and v.lower() in PLACEHOLDER_SECRETS:
                # Only reject obvious placeholders here. Unlike JWT_SECRET,
                # these are interactive login passwords generated by
                # scripts/init_env.py (~12 chars), so the 32-char secret rule
                # does not apply.
                problems.append(f"{name} (placeholder)")
        return problems


settings = Settings()
