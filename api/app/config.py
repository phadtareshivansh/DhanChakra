from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "dhanchakra123"
    
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "dhanchakra"
    postgres_password: str = "dhanchakra123"
    postgres_db: str = "dhanchakra"
    
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

settings = Settings()