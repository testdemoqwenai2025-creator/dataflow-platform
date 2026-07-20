"""
FastAPI application factory and entry point.

This module creates and configures the FastAPI application with:

    1. All API routers mounted under /api/v1
    2. CORS middleware for cross-origin requests
    3. Rate limiting middleware for abuse prevention
    4. Auth middleware for protected route enforcement
    5. WebSocket endpoint for real-time query updates
    6. Startup/shutdown lifecycle events for database connections
    7. OpenAPI documentation configuration

Architecture Decision:
    We use the "application factory" pattern — `create_app()` returns a
    fully configured FastAPI instance. This enables:
        - Clean separation of configuration from execution
        - Multiple app instances for testing with different configs
        - Easy integration with ASGI servers (uvicorn, gunicorn)

    The lifespan context manager (FastAPI's recommended approach) handles
    startup/shutdown, replacing the older @app.on_event decorators.
"""

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware import Middleware

from app.core.config import settings
from app.core.database import init_databases, close_databases
from app.middleware.cors import add_cors_middleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.auth_middleware import AuthMiddleware

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── WebSocket Connection Manager ──────────────────────────────────────────

class ConnectionManager:
    """
    Manages active WebSocket connections for real-time updates.

    Supports:
        - Broadcasting messages to all connected clients
        - Sending messages to specific users
        - Automatic cleanup on disconnect

    Use cases:
        - Real-time query progress updates
        - Dashboard data refresh notifications
        - Collaborative editing notifications
    """

    def __init__(self):
        # active_connections: {websocket: user_id}
        self.active_connections: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, user_id: str = "anonymous") -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self.active_connections[websocket] = user_id
        logger.info(
            "WebSocket connected: user=%s (total: %d)",
            user_id,
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection."""
        user_id = self.active_connections.pop(websocket, "unknown")
        logger.info(
            "WebSocket disconnected: user=%s (remaining: %d)",
            user_id,
            len(self.active_connections),
        )

    async def broadcast(self, message: dict) -> None:
        """
        Send a message to all connected clients.

        Args:
            message: Dictionary that will be JSON-encoded before sending.
        """
        payload = json.dumps(message)
        disconnected = []

        for websocket in self.active_connections:
            try:
                await websocket.send_text(payload)
            except Exception as exc:
                logger.warning("Failed to send to WebSocket: %s", exc)
                disconnected.append(websocket)

        # Clean up failed connections
        for ws in disconnected:
            self.disconnect(ws)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        """Send a message to all connections belonging to a specific user."""
        payload = json.dumps(message)
        for ws, uid in self.active_connections.items():
            if uid == user_id:
                try:
                    await ws.send_text(payload)
                except Exception:
                    self.disconnect(ws)


# Global connection manager instance
ws_manager = ConnectionManager()


# ── Application Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan context manager.

    Handles startup and shutdown events:
        - Startup: Initialise database connections
        - Shutdown: Close database connections gracefully

    This replaces the deprecated @app.on_event("startup") /
    @app.on_event("shutdown") pattern.
    """
    # ── Startup ──
    logger.info(
        "🚀 Starting %s v%s (%s)",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.ENVIRONMENT,
    )

    try:
        await init_databases()
        logger.info("✅ Databases initialised")
    except Exception as exc:
        logger.error("❌ Database initialisation failed: %s", exc)
        if settings.is_production:
            raise
        logger.warning("⚠️  Continuing without full database support")

    logger.info("🎧 API server ready")

    yield  # Application runs here

    # ── Shutdown ──
    logger.info("🛑 Shutting down %s", settings.APP_NAME)

    # Close all WebSocket connections
    for ws in list(ws_manager.active_connections.keys()):
        try:
            await ws.close()
        except Exception:
            pass
    ws_manager.active_connections.clear()

    # Close database connections
    await close_databases()
    logger.info("👋 Goodbye!")


# ── App Factory ───────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    This is the main entry point for the application. It:
        1. Creates the FastAPI instance with OpenAPI metadata
        2. Adds middleware (CORS, rate limiting, auth)
        3. Includes all API routers
        4. Registers the WebSocket endpoint

    Returns:
        A fully configured FastAPI application instance.
    """
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "A powerful data analytics platform with DuckDB for analytical "
            "queries and PostgreSQL for transactional data. Features include "
            "SQL query execution, dataset management, aggregation, pivot tables, "
            "dashboards, and real-time updates via WebSocket."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── Middleware (order matters — outermost first) ──
    # 1. CORS — must be outermost so preflight requests are handled
    add_cors_middleware(app)

    # 2. Rate limiting — applied to all requests including auth
    app.add_middleware(RateLimitMiddleware, max_requests=settings.RATE_LIMIT_PER_MINUTE)

    # 3. Auth — validates JWT tokens and sets request state
    # Note: We add this as a pure ASGI middleware
    app.add_middleware(AuthMiddleware)

    # ── Include API Routers ──
    _register_routers(app)

    # ── WebSocket Endpoint ──
    _register_websocket(app)

    # ── Request Logging Middleware ──
    _add_request_logging(app)

    return app


def _register_routers(app: FastAPI) -> None:
    """
    Register all API routers with the application.

    All routers are mounted under /api/v1 prefix for versioning.
    When v2 endpoints are needed, they can be added alongside v1
    without breaking existing clients.
    """
    from app.api.v1.endpoints import router as endpoints_router
    from app.api.v1.auth import router as auth_router
    from app.api.v1.data import router as data_router
    from app.api.v1.analytics import router as analytics_router

    # Health & info endpoints (no auth required)
    app.include_router(endpoints_router, prefix="/api/v1", tags=["Health & Info"])

    # Authentication endpoints
    app.include_router(auth_router, prefix="/api/v1")

    # Data management endpoints
    app.include_router(data_router, prefix="/api/v1")

    # Analytics endpoints
    app.include_router(analytics_router, prefix="/api/v1")

    logger.info("Registered 4 API routers under /api/v1")


def _register_websocket(app: FastAPI) -> None:
    """
    Register the WebSocket endpoint for real-time updates.

    The WebSocket endpoint supports:
        - Real-time query execution progress
        - Dashboard update notifications
        - Dataset change notifications

    Protocol:
        Clients send JSON messages with a "type" field:
            - "subscribe": Subscribe to a channel (e.g., "queries", "dashboard")
            - "unsubscribe": Unsubscribe from a channel
            - "ping": Keep-alive ping

        Server sends JSON messages:
            - "pong": Response to ping
            - "query_progress": Query execution progress
            - "query_result": Query completion notification
            - "dataset_updated": Dataset change notification
            - "dashboard_updated": Dashboard config change
    """

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """
        WebSocket endpoint for real-time updates.

        Accepts connections and processes incoming messages.
        Broadcasts relevant events to subscribed clients.
        """
        await ws_manager.connect(websocket)
        subscribed_channels: Set[str] = set()

        try:
            while True:
                # Receive and parse message
                raw = await websocket.receive_text()

                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "detail": "Invalid JSON",
                    }))
                    continue

                msg_type = message.get("type", "")

                if msg_type == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": time.time(),
                    }))

                elif msg_type == "subscribe":
                    channel = message.get("channel", "")
                    if channel:
                        subscribed_channels.add(channel)
                        await websocket.send_text(json.dumps({
                            "type": "subscribed",
                            "channel": channel,
                            "channels": list(subscribed_channels),
                        }))

                elif msg_type == "unsubscribe":
                    channel = message.get("channel", "")
                    subscribed_channels.discard(channel)
                    await websocket.send_text(json.dumps({
                        "type": "unsubscribed",
                        "channel": channel,
                        "channels": list(subscribed_channels),
                    }))

                elif msg_type == "query":
                    # Execute a query and stream results back
                    sql = message.get("sql", "")
                    if sql:
                        await websocket.send_text(json.dumps({
                            "type": "query_started",
                            "sql": sql,
                        }))

                        try:
                            from app.core.database import get_duckdb_connection
                            from app.services.query_service import QueryService

                            conn = get_duckdb_connection()
                            service = QueryService(conn)

                            start_time = time.time()
                            df = service.execute_query(sql)
                            execution_time = (time.time() - start_time) * 1000

                            # Send results (limit to 100 rows for WebSocket)
                            rows = df.head(100).to_dict(orient="records")
                            # Clean numpy types
                            clean_rows = []
                            for row in rows:
                                clean_row = {}
                                for k, v in row.items():
                                    import pandas as pd
                                    if pd.isna(v):
                                        clean_row[k] = None
                                    elif hasattr(v, "item"):
                                        clean_row[k] = v.item()
                                    else:
                                        clean_row[k] = v
                                clean_rows.append(clean_row)

                            await websocket.send_text(json.dumps({
                                "type": "query_result",
                                "columns": df.columns.tolist(),
                                "rows": clean_rows,
                                "row_count": len(df),
                                "execution_time_ms": round(execution_time, 2),
                                "truncated": len(df) > 100,
                            }))

                        except Exception as exc:
                            await websocket.send_text(json.dumps({
                                "type": "query_error",
                                "detail": str(exc),
                            }))

                else:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "detail": f"Unknown message type: {msg_type}",
                    }))

        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
            logger.info("WebSocket client disconnected normally")
        except Exception as exc:
            logger.error("WebSocket error: %s", exc)
            ws_manager.disconnect(websocket)


def _add_request_logging(app: FastAPI) -> None:
    """
    Add request/response logging middleware.

    Logs each request with method, path, status code, and duration.
    This is useful for debugging and performance monitoring.
    """

    @app.middleware("http")
    async def log_requests(request, call_next):
        start_time = time.time()

        # Process the request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000

        # Log (skip health checks to reduce noise)
        path = request.url.path
        if path not in ("/health", "/docs", "/redoc", "/openapi.json"):
            logger.info(
                "%s %s → %d (%.1fms)",
                request.method,
                path,
                response.status_code,
                duration_ms,
            )

        return response


# ── Application Instance ──────────────────────────────────────────────────
# This is what uvicorn imports: `uvicorn app.main:app`
app = create_app()


# ── Direct Execution ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.is_development,
        log_level="debug" if settings.DEBUG else "info",
    )
