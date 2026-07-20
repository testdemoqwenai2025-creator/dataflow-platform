"""
Database connection management.

This module provides dual-database support:

    1. **DuckDB** — Embedded columnar database for OLAP / analytical queries.
       Ideal for scanning large Parquet/CSV datasets with SQL at high speed.
       Connection lifecycle: one shared connection per process (DuckDB is
       single-writer by design). We use a contextmanager to ensure the
       connection is properly returned after each operation.

    2. **PostgreSQL** (via SQLAlchemy) — Relational database for OLTP /
       transactional workloads: user accounts, dataset metadata, audit logs.
       Uses SQLAlchemy's async-compatible sessionmaker for clean dependency
       injection into FastAPI endpoints.

Architecture Decision:
    We intentionally separate analytical and transactional data stores.
    DuckDB excels at columnar scans but is single-writer; PostgreSQL handles
    concurrent writes and complex relational constraints. This separation
    allows each engine to operate at its strengths without contention.
"""

import logging
from contextlib import contextmanager
from typing import Generator, AsyncGenerator

import duckdb
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from fastapi import Depends

from app.core.config import settings

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# PostgreSQL (SQLAlchemy ORM)
# ═══════════════════════════════════════════════════════════════════════════

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


def _build_postgres_engine():
    """
    Build the SQLAlchemy engine for PostgreSQL.

    Pool configuration:
        - pool_size=5:      Number of persistent connections to keep open.
        - max_overflow=10:  Additional connections allowed during bursts.
        - pool_recycle=3600: Recycle connections hourly to avoid stale sockets.
        - pool_pre_ping=True: Verify liveness before each checkout.
        - echo=False:        SQL logging controlled via DEBUG flag.
    """
    engine = create_engine(
        settings.POSTGRES_URL,
        pool_size=5,
        max_overflow=10,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=settings.DEBUG,
    )

    # Optimise PostgreSQL for analytical helper queries
    @event.listens_for(engine, "connect")
    def _set_search_path(dbapi_connection, connection_record):
        """Set default schema search path on each new connection."""
        cursor = dbapi_connection.cursor()
        cursor.execute("SET search_path TO public")
        cursor.close()

    return engine


# Engine is created lazily but stored module-level for reuse.
# In production, consider using a connection pooler like PgBouncer.
_engine = None
_SessionLocal = None


def get_postgres_engine():
    """Return the SQLAlchemy engine, creating it on first call."""
    global _engine
    if _engine is None:
        logger.info("Initializing PostgreSQL engine: %s", settings.POSTGRES_URL.split("@")[-1])
        _engine = _build_postgres_engine()
    return _engine


def get_session_local():
    """Return the session factory, creating it on first call."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_postgres_engine(),
        )
    return _SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a SQLAlchemy Session for PostgreSQL.

    Usage in endpoint:
        @router.get("/users")
        def list_users(db: Session = Depends(get_db)):
            ...

    The session is automatically closed after the request completes,
    even if an exception occurs.
    """
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════════
# DuckDB (Analytical Engine)
# ═══════════════════════════════════════════════════════════════════════════

_duckdb_connection: duckdb.DuckDBPyConnection | None = None


def _get_duckdb_path() -> str:
    """
    Extract the file path from the DuckDB connection string.

    The DATABASE_URL is expected in the format:
        duckdb:///path/to/file.duckdb   (absolute path, 3 slashes)
        duckdb://path/to/file.duckdb    (relative path, 2 slashes)

    For an in-memory database:
        duckdb:///:memory:  or  duckdb://memory
    """
    url = settings.DATABASE_URL
    if url.startswith("duckdb:///"):
        # Absolute path or special name after the triple slash
        path = url[len("duckdb:///"):]
        return path if path else ":memory:"
    elif url.startswith("duckdb://"):
        path = url[len("duckdb://"):]
        return path if path else ":memory:"
    # Fallback: treat as a plain path or :memory:
    return url


def get_duckdb_connection() -> duckdb.DuckDBPyConnection:
    """
    Return the shared DuckDB connection, creating it on first call.

    DuckDB uses a single-writer model, so we share one connection across
    the application. Read queries can execute concurrently; writes are
    serialised by DuckDB internally.

    Configuration applied on first creation:
        - memory_limit: Prevents runaway queries from consuming all RAM.
        - threads: Controls parallelism for scan/aggregation operators.
    """
    global _duckdb_connection
    if _duckdb_connection is None:
        path = _get_duckdb_path()
        logger.info("Initializing DuckDB connection: %s", path)

        _duckdb_connection = duckdb.connect(path)

        # Apply performance configuration
        try:
            _duckdb_connection.execute(
                f"SET memory_limit='{settings.DUCKDB_MEMORY_LIMIT}'"
            )
            _duckdb_connection.execute(
                f"SET threads={settings.DUCKDB_THREADS}"
            )
            logger.info(
                "DuckDB configured: memory_limit=%s, threads=%s",
                settings.DUCKDB_MEMORY_LIMIT,
                settings.DUCKDB_THREADS,
            )
        except Exception as exc:
            logger.warning("DuckDB configuration warning: %s", exc)

    return _duckdb_connection


@contextmanager
def get_duckdb() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """
    Context-manager dependency for DuckDB access in FastAPI endpoints.

    Usage:
        @router.post("/query")
        def run_query(conn: duckdb.DuckDBPyConnection = Depends(get_duckdb)):
            result = conn.execute("SELECT 1").fetchall()

    We use a contextmanager (instead of a plain dependency) so that
    transaction state can be managed predictably — each request gets
    a clean transaction scope.
    """
    conn = get_duckdb_connection()
    try:
        yield conn
    except Exception:
        # Roll back any pending transaction on error
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise


# ═══════════════════════════════════════════════════════════════════════════
# Lifecycle helpers (called from main.py startup/shutdown)
# ═══════════════════════════════════════════════════════════════════════════

async def init_databases():
    """
    Initialise both database connections at application startup.

    This is called from the FastAPI lifespan handler. We eagerly
    connect so that any configuration errors surface immediately
    rather than on the first request.
    """
    # Initialise DuckDB
    try:
        conn = get_duckdb_connection()
        # Quick sanity check
        result = conn.execute("SELECT 1 AS sanity").fetchone()
        logger.info("DuckDB initialised — sanity check: %s", result)
    except Exception as exc:
        logger.error("Failed to initialise DuckDB: %s", exc)
        raise

    # Initialise PostgreSQL
    try:
        engine = get_postgres_engine()
        with engine.connect() as conn:
            result = conn.execute(__import__("sqlalchemy").text("SELECT 1"))
            logger.info("PostgreSQL initialised — sanity check: %s", result.scalar())
    except Exception as exc:
        logger.warning(
            "PostgreSQL not available (this is OK if only using DuckDB): %s", exc
        )


async def close_databases():
    """
    Gracefully close all database connections at application shutdown.

    Ensures that in-flight writes are flushed and file handles released.
    """
    global _duckdb_connection, _engine

    if _duckdb_connection is not None:
        try:
            _duckdb_connection.close()
            logger.info("DuckDB connection closed")
        except Exception as exc:
            logger.warning("Error closing DuckDB: %s", exc)
        _duckdb_connection = None

    if _engine is not None:
        try:
            _engine.dispose()
            logger.info("PostgreSQL engine disposed")
        except Exception as exc:
            logger.warning("Error disposing PostgreSQL engine: %s", exc)
        _engine = None
