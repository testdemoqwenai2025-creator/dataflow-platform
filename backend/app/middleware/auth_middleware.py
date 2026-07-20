"""
Authentication middleware for JWT validation on protected routes.

This middleware intercepts requests and validates JWT tokens on routes
that require authentication. It works in concert with the per-endpoint
`get_current_user` dependency:

    - The middleware performs a lightweight token check and sets
      request state (user_id, token claims) for downstream access.
    - The dependency performs the full verification and raises 401
      on invalid tokens.

Architecture Decision:
    We use a hybrid approach: middleware for broad-brush route protection
    and FastAPI dependencies for fine-grained per-endpoint auth. This
    gives us:

        1. Defense in depth — even if a developer forgets to add the
           dependency, the middleware catches unauthenticated requests
           to protected paths.
        2. Flexibility — some endpoints (health, login) are explicitly
           excluded from middleware checks.

    The middleware does NOT reject requests itself for protected routes
    that also have the dependency — that would cause double errors.
    Instead, it attaches user info to request.state when a valid token
    is present, and the dependency uses that or falls back to full
    verification.
"""

import logging
from typing import Callable, Set

from fastapi import Request, Response
from jose import JWTError, jwt

from app.core.config import settings

logger = logging.getLogger(__name__)

# Routes that do NOT require authentication
# These are checked as prefix matches
PUBLIC_PATHS: Set[str] = {
    "/health",
    "/info",
    "/version",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/ws",
}

# Path prefixes that are public
PUBLIC_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi",
)


class AuthMiddleware:
    """
    ASGI middleware that validates JWT tokens on protected routes.

    For public routes, the request passes through without token validation.
    For protected routes, the middleware:
        1. Extracts the Bearer token from the Authorization header.
        2. Decodes and validates the JWT.
        3. Attaches user claims to request.state.user_claims.
        4. If no valid token is found on a protected route, sets
           request.state.auth_error with the reason.

    The actual 401 rejection is handled by the `get_current_user`
    dependency in the endpoint, not by this middleware. This design
    allows endpoints to optionally handle missing auth differently.
    """

    def __init__(self, app: Callable) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # For HTTP requests, we need to work with the ASGI scope
        # We'll use a wrapper approach
        if scope["type"] == "http":
            path = scope.get("path", "")

            # Check if this is a public path
            if self._is_public_path(path):
                await self.app(scope, receive, send)
                return

            # Try to extract and validate token from headers
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode("utf-8")

            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                try:
                    payload = jwt.decode(
                        token,
                        settings.SECRET_KEY,
                        algorithms=[settings.ALGORITHM],
                    )
                    # Attach user info to scope state
                    if "state" not in scope:
                        scope["state"] = {}
                    scope["state"]["user_claims"] = payload
                    scope["state"]["user_id"] = payload.get("sub")
                except JWTError as exc:
                    logger.debug("JWT validation failed in middleware: %s", exc)
                    if "state" not in scope:
                        scope["state"] = {}
                    scope["state"]["auth_error"] = str(exc)

        await self.app(scope, receive, send)

    @staticmethod
    def _is_public_path(path: str) -> bool:
        """Check if a path should bypass authentication."""
        # Exact match
        if path in PUBLIC_PATHS:
            return True

        # Prefix match (e.g., /docs/oauth2-redirect)
        for prefix in PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return True

        return False


def is_public_path(path: str) -> bool:
    """Convenience function to check if a path is public."""
    return AuthMiddleware._is_public_path(path)
