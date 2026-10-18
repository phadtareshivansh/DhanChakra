from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


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
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_page_size: int = 100

    # --- Auth ---
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # --- Demo user seeding (optional; skipped unless configured + enabled) ---
    seed_demo_users: bool = False
    demo_admin_email: Optional[str] = None
    demo_admin_password: Optional[str] = None
    demo_admin_name: str = "Demo Admin"
    demo_analyst_email: Optional[str] = None
    demo_analyst_password: Optional[str] = None
    demo_analyst_name: str = "Demo Analyst"

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

    # --- Graph analytics ---
    max_cycle_hops: int = 8
    min_cycle_length: int = 3
    max_neighborhood_hops: int = 5
    default_neighborhood_hops: int = 2
    loops_default_max_length: int = 6
    weak_label_threshold: float = 40
    entity_resolution_fuzzy_threshold: float = 0.92

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


settings = Settings()
