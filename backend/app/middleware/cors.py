"""
CORS middleware configuration.

Configures Cross-Origin Resource Sharing (CORS) to allow the frontend
application (typically running on a different port in development) to
communicate with the backend API.

Architecture Decision:
    We configure CORS via FastAPI's built-in CORSMiddleware rather than
    a custom implementation. This is well-tested, performant, and handles
    preflight OPTIONS requests correctly.

    In production, CORS origins should be restricted to the actual
    frontend domain(s). In development, we allow common localhost ports.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)


def add_cors_middleware(app: FastAPI) -> None:
    """
    Add CORS middleware to the FastAPI application.

    Configuration is loaded from settings.CORS_ORIGINS (comma-separated
    list of allowed origins).

    Args:
        app: The FastAPI application instance.

    CORS Policy:
        - allow_origins: Only origins listed in settings are permitted.
            Use ["*"] only in development — never in production.
        - allow_credentials: True — required for sending cookies/auth headers.
        - allow_methods: All standard HTTP methods are allowed.
        - allow_headers: All headers are allowed (needed for Authorization).
    """
    origins = settings.cors_origins_list

    # In development mode, add common localhost ports if not already present
    if settings.is_development:
        dev_origins = [
            "http://localhost:3000",
            "http://localhost:3001",
            "http://localhost:8000",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8000",
        ]
        for origin in dev_origins:
            if origin not in origins:
                origins.append(origin)

    logger.info(
        "CORS middleware configured with %d allowed origins: %s",
        len(origins),
        origins if len(origins) <= 5 else f"{origins[:5]}... (+{len(origins) - 5} more)",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "Content-Disposition",  # Needed for file downloads
            "X-Request-ID",
        ],
    )
