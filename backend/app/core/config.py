"""
Application configuration module.

Uses pydantic-settings to manage environment-based configuration with sensible defaults.
All settings can be overridden via environment variables or a .env file.

Architecture Decision:
    We centralize all configuration here so that every module imports from a single
    source of truth. This avoids scattered magic strings and makes deployment across
    dev/staging/prod environments straightforward — just change env vars.
"""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """
    Central application settings.

    Values are loaded in this priority order (highest wins):
        1. Environment variables
        2. .env file (if present)
        3. Defaults defined here

    Attributes:
        DATABASE_URL: DuckDB connection string for analytical workloads.
            DuckDB is an embedded columnar database ideal for OLAP queries on
            local/Parquet/CSV data without a separate server process.
        POSTGRES_URL: PostgreSQL connection string for transactional data.
            Used for user accounts, metadata, audit logs — data that requires
            ACID guarantees and concurrent writes.
        SECRET_KEY: JWT signing key. MUST be changed in production.
        ALGORITHM: JWT algorithm (default HS256).
        ACCESS_TOKEN_EXPIRE_MINUTES: JWT lifetime in minutes.
        CORS_ORIGINS: Comma-separated list of allowed origins for CORS.
        REDIS_URL: Redis connection for rate limiting / caching (optional).
        ENVIRONMENT: Runtime environment — dev, staging, or prod.
        APP_NAME: Display name of the application.
        APP_VERSION: Semantic version string.
        DEBUG: Enable debug mode (verbose logging, tracebacks).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Database ──────────────────────────────────────────────────────────
    # DuckDB is used as the primary analytical engine. Its file-based nature
    # means zero infrastructure overhead for development, while still offering
    # full SQL support and excellent columnar scan performance.
    DATABASE_URL: str = Field(
        default="duckdb:///data/analytics.duckdb",
        description="DuckDB connection string for analytical queries",
    )

    # PostgreSQL handles transactional workloads — user accounts, dataset
    # metadata, audit trails — where row-level locking and ACID compliance
    # are required.
    POSTGRES_URL: str = Field(
        default="postgresql://user:pass@localhost:5432/dataflow",
        description="PostgreSQL connection string for transactional data",
    )

    # ── Authentication ────────────────────────────────────────────────────
    SECRET_KEY: str = Field(
        default="super-secret-key-change-in-production-0987654321",
        description="JWT signing key — MUST be changed in production",
    )
    ALGORITHM: str = Field(
        default="HS256",
        description="JWT signing algorithm",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        description="JWT token lifetime in minutes",
    )

    # ── CORS ──────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000,http://127.0.0.1:3000",
        description="Comma-separated allowed CORS origins",
    )

    # ── Redis ─────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for rate limiting and caching",
    )

    # ── Application ───────────────────────────────────────────────────────
    ENVIRONMENT: str = Field(
        default="dev",
        description="Runtime environment: dev | staging | prod",
    )
    APP_NAME: str = Field(
        default="DataFlow Platform",
        description="Application display name",
    )
    APP_VERSION: str = Field(
        default="1.0.0",
        description="Semantic version",
    )
    DEBUG: bool = Field(
        default=True,
        description="Enable debug mode (verbose logging, detailed errors)",
    )

    # ── Rate Limiting ─────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = Field(
        default=60,
        description="Maximum requests per minute per IP",
    )

    # ── DuckDB-specific ───────────────────────────────────────────────────
    DUCKDB_MEMORY_LIMIT: str = Field(
        default="2GB",
        description="DuckDB memory limit for query execution",
    )
    DUCKDB_THREADS: int = Field(
        default=4,
        description="Number of threads DuckDB may use",
    )

    # ── Helpers ───────────────────────────────────────────────────────────

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse the comma-separated CORS_ORIGINS into a list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        """Check if the app is running in production."""
        return self.ENVIRONMENT.lower() == "prod"

    @property
    def is_development(self) -> bool:
        """Check if the app is running in development."""
        return self.ENVIRONMENT.lower() == "dev"


# Singleton instance — imported by other modules as:
#   from app.core.config import settings
settings = Settings()
