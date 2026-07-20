"""
Health check, API info, and versioned endpoint registry.

These endpoints are unauthenticated and provide operational visibility
into the running service. They are typically used by:
    - Load balancers / Kubernetes liveness probes
    - Monitoring dashboards
    - API consumers discovering available endpoints
"""

import time
import logging
from typing import Dict

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.database import get_duckdb_connection
from app.models.schemas import HealthResponse, APIInfoResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health & Info"])

# Track application start time for uptime calculation
_start_time = time.time()


def _check_duckdb() -> str:
    """Check DuckDB connectivity by running a lightweight query."""
    try:
        conn = get_duckdb_connection()
        result = conn.execute("SELECT 1").fetchone()
        return "healthy" if result == (1,) else "degraded"
    except Exception as exc:
        logger.error("DuckDB health check failed: %s", exc)
        return "unhealthy"


def _check_postgres() -> str:
    """Check PostgreSQL connectivity (graceful degradation if unavailable)."""
    try:
        from app.core.database import get_postgres_engine
        engine = get_postgres_engine()
        with engine.connect() as conn:
            from sqlalchemy import text
            result = conn.execute(text("SELECT 1"))
            return "healthy" if result.scalar() == 1 else "degraded"
    except Exception as exc:
        logger.warning("PostgreSQL health check failed: %s", exc)
        return "unavailable"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the health status of the service and its dependencies.",
)
async def health_check() -> HealthResponse:
    """
    Lightweight health check endpoint.

    Used by infrastructure (load balancers, Kubernetes) to determine
    if the service is alive and its dependencies are reachable.

    The check queries both DuckDB and PostgreSQL with a simple
    `SELECT 1` to verify connectivity.
    """
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        duckdb_status=_check_duckdb(),
        postgres_status=_check_postgres(),
        uptime_seconds=round(time.time() - _start_time, 2),
    )


@router.get(
    "/info",
    response_model=APIInfoResponse,
    summary="API information",
    description="Returns metadata about the API and its available endpoints.",
)
async def api_info() -> APIInfoResponse:
    """
    API discovery endpoint.

    Returns a machine-readable description of the API including
    name, version, and a list of all registered endpoint groups
    with their paths and descriptions.
    """
    endpoint_groups = [
        {
            "path": "/api/v1/auth",
            "description": "Authentication and user management",
            "endpoints": ["POST /register", "POST /login", "POST /refresh", "GET /me"],
        },
        {
            "path": "/api/v1/data",
            "description": "Dataset management and SQL queries",
            "endpoints": [
                "GET /datasets",
                "POST /upload",
                "GET /datasets/{id}",
                "DELETE /datasets/{id}",
                "POST /query",
                "GET /export/{id}",
            ],
        },
        {
            "path": "/api/v1/analytics",
            "description": "Aggregation, pivot tables, dashboards, and statistics",
            "endpoints": [
                "POST /aggregate",
                "POST /pivot",
                "GET /dashboard",
                "PUT /dashboard",
                "GET /stats/{dataset_id}",
            ],
        },
    ]

    return APIInfoResponse(
        name=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="A powerful data analytics platform with DuckDB and PostgreSQL backends.",
        endpoints=endpoint_groups,
    )


@router.get(
    "/version",
    summary="Version information",
    description="Returns the current API version.",
)
async def version() -> Dict[str, str]:
    """Minimal version endpoint for quick checks."""
    return {
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "app_name": settings.APP_NAME,
    }
