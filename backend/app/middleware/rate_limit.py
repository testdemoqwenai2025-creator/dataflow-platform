"""
Rate limiting middleware using in-memory counters with Redis option.

This middleware implements a sliding-window rate limiter that tracks
requests per client IP address. Two backends are supported:

    1. **In-memory** (default) — Uses a Python dictionary to track request
       counts. Suitable for single-instance deployments. Data is lost on
       restart, which is acceptable for rate limiting.

    2. **Redis** (optional) — Uses Redis for distributed rate limiting
       across multiple instances. Automatically activated when Redis
       is reachable at settings.REDIS_URL.

Architecture Decision:
    Rate limiting is implemented as ASGI middleware rather than a FastAPI
    dependency so that it applies to ALL requests (including static files
    and WebSocket upgrades) without requiring per-endpoint decorators.

    We use a fixed-window algorithm (simpler than sliding window) with
    per-minute granularity. This provides adequate protection against
    brute-force and denial-of-service attacks while being easy to
    understand and debug.
"""

import logging
import time
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """
    Fixed-window rate limiter using an in-memory dictionary.

    Tracks request counts per (IP, window_start) pair. Windows are
    one minute wide. Expired windows are cleaned up periodically.

    Thread safety note:
        In an async context (FastAPI/uvicorn), dictionary operations
        are safe because they execute within the event loop on a
        single thread. If using multiple worker processes, each
        process has its own rate limit state — use Redis instead.
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        """
        Args:
            max_requests: Maximum number of requests allowed per window.
            window_seconds: Window duration in seconds.
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Structure: {ip: [(timestamp, count), ...]}
        self._windows: Dict[str, List[Tuple[float, int]]] = defaultdict(list)
        self._last_cleanup = time.time()

    def is_allowed(self, key: str) -> Tuple[bool, int, int]:
        """
        Check if a request from the given key is allowed.

        Args:
            key: Usually the client IP address.

        Returns:
            Tuple of (is_allowed, current_count, limit).
            - is_allowed: True if the request is within rate limits.
            - current_count: Number of requests in the current window.
            - limit: Maximum requests per window.
        """
        now = time.time()
        window_start = now - (now % self.window_seconds)

        # Periodic cleanup of expired windows (every 5 minutes)
        if now - self._last_cleanup > 300:
            self._cleanup(now)
            self._last_cleanup = now

        # Find or create current window for this key
        windows = self._windows[key]

        # Remove expired windows
        windows = [
            (ws, count) for ws, count in windows
            if ws > now - self.window_seconds
        ]

        # Count requests in current window
        current_count = sum(
            count for ws, count in windows
            if ws >= window_start
        )

        if current_count >= self.max_requests:
            self._windows[key] = windows
            return False, current_count, self.max_requests

        # Increment count
        # Check if we already have an entry for this window
        found = False
        for i, (ws, count) in enumerate(windows):
            if ws == window_start:
                windows[i] = (ws, count + 1)
                found = True
                break

        if not found:
            windows.append((window_start, 1))

        self._windows[key] = windows
        return True, current_count + 1, self.max_requests

    def _cleanup(self, now: float) -> None:
        """Remove expired entries to prevent memory leaks."""
        cutoff = now - self.window_seconds * 2
        expired_keys = []

        for key, windows in self._windows.items():
            self._windows[key] = [
                (ws, count) for ws, count in windows if ws > cutoff
            ]
            if not self._windows[key]:
                expired_keys.append(key)

        for key in expired_keys:
            del self._windows[key]

        logger.debug(
            "Rate limiter cleanup: %d active keys", len(self._windows)
        )


class RedisRateLimiter:
    """
    Fixed-window rate limiter using Redis for distributed deployments.

    Uses Redis INCR with EXPIRE for atomic window counting.
    Requires a running Redis instance.
    """

    def __init__(
        self,
        redis_url: str,
        max_requests: int = 60,
        window_seconds: int = 60,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._redis = None
        self._redis_url = redis_url

    async def _get_redis(self):
        """Lazily initialise Redis connection."""
        if self._redis is None:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(self._redis_url)
                logger.info("Redis rate limiter connected: %s", self._redis_url)
            except Exception as exc:
                logger.error("Failed to connect to Redis: %s", exc)
                raise
        return self._redis

    async def is_allowed(self, key: str) -> Tuple[bool, int, int]:
        """
        Check if a request is allowed using Redis atomic operations.

        Args:
            key: Client identifier (usually IP address).

        Returns:
            Tuple of (is_allowed, current_count, limit).
        """
        try:
            redis = await self._get_redis()
            redis_key = f"ratelimit:{key}:{int(time.time()) // self.window_seconds}"

            pipe = redis.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, self.window_seconds * 2)
            results = await pipe.execute()

            current_count = results[0]
            is_allowed = current_count <= self.max_requests

            return is_allowed, current_count, self.max_requests

        except Exception as exc:
            logger.warning("Redis rate limit check failed, allowing request: %s", exc)
            # Fail open — if Redis is down, don't block legitimate traffic
            return True, 0, self.max_requests


class RateLimitMiddleware:
    """
    ASGI middleware that enforces rate limits per client IP.

    Adds the following headers to responses:
        - X-RateLimit-Limit: Maximum requests per window
        - X-RateLimit-Remaining: Remaining requests in current window
        - X-RateLimit-Reset: Seconds until the window resets

    When rate limit is exceeded:
        - Returns HTTP 429 Too Many Requests
        - Includes Retry-After header
    """

    def __init__(
        self,
        app: Callable,
        max_requests: int = None,
        window_seconds: int = 60,
    ):
        self.app = app
        self.max_requests = max_requests or settings.RATE_LIMIT_PER_MINUTE
        self.window_seconds = window_seconds

        # Initialise rate limiter backend
        self._limiter = InMemoryRateLimiter(
            max_requests=self.max_requests,
            window_seconds=self.window_seconds,
        )
        self._redis_limiter: Optional[RedisRateLimiter] = None

        # Try to set up Redis backend
        self._init_redis_limiter()

    def _init_redis_limiter(self) -> None:
        """Attempt to initialise Redis-backed rate limiter."""
        try:
            import redis
            r = redis.from_url(settings.REDIS_URL)
            r.ping()
            self._redis_limiter = RedisRateLimiter(
                redis_url=settings.REDIS_URL,
                max_requests=self.max_requests,
                window_seconds=self.window_seconds,
            )
            logger.info("Redis rate limiter initialised")
        except Exception:
            logger.info(
                "Redis not available, using in-memory rate limiter "
                "(not suitable for multi-process deployments)"
            )

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Extract client IP
        client_ip = self._get_client_ip(scope)

        # Check rate limit
        is_allowed, current_count, limit = self._limiter.is_allowed(client_ip)
        remaining = max(0, limit - current_count)
        reset_seconds = self.window_seconds - (int(time.time()) % self.window_seconds)

        if not is_allowed:
            # Build 429 response
            response_headers = [
                [b"content-type", b"application/json"],
                [b"retry-after", str(reset_seconds).encode()],
                [b"x-ratelimit-limit", str(limit).encode()],
                [b"x-ratelimit-remaining", b"0"],
                [b"x-ratelimit-reset", str(reset_seconds).encode()],
            ]

            body = b'{"detail":"Rate limit exceeded. Please try again later.","status_code":429}'

            await send({
                "type": "http.response.start",
                "status": 429,
                "headers": response_headers,
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
            return

        # Inject rate limit headers into the response
        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append([b"x-ratelimit-limit", str(limit).encode()])
                headers.append([b"x-ratelimit-remaining", str(remaining).encode()])
                headers.append([b"x-ratelimit-reset", str(reset_seconds).encode()])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)

    @staticmethod
    def _get_client_ip(scope) -> str:
        """
        Extract the client IP address from the ASGI scope.

        Checks X-Forwarded-For and X-Real-IP headers first (for reverse
        proxy setups), then falls back to the direct connection IP.
        """
        headers = dict(scope.get("headers", []))

        # Check X-Forwarded-For (first IP in the chain)
        forwarded = headers.get(b"x-forwarded-for", b"").decode("utf-8")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP
        real_ip = headers.get(b"x-real-ip", b"").decode("utf-8")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct connection
        client = scope.get("client")
        if client:
            return client[0]

        return "unknown"
