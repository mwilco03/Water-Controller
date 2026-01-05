"""
Water Treatment Controller - Rate Limiting Middleware
Copyright (C) 2024-2025
SPDX-License-Identifier: GPL-3.0-or-later

Token bucket rate limiting for API protection.
Prevents DoS attacks and brute-force attempts.

Configuration via environment:
    WTC_RATE_LIMIT_ENABLED=true
    WTC_RATE_LIMIT_REQUESTS=100  # requests per window
    WTC_RATE_LIMIT_WINDOW=60     # window in seconds
    WTC_RATE_LIMIT_BURST=20      # burst allowance
"""

import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .logging import get_logger

logger = get_logger(__name__)


@dataclass
class TokenBucket:
    """Token bucket for rate limiting."""
    capacity: float
    tokens: float
    refill_rate: float  # tokens per second
    last_refill: float = field(default_factory=time.monotonic)

    def consume(self, tokens: int = 1) -> bool:
        """
        Attempt to consume tokens.
        Returns True if successful, False if rate limited.
        """
        now = time.monotonic()
        elapsed = now - self.last_refill

        # Refill tokens based on elapsed time
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    @property
    def retry_after(self) -> float:
        """Seconds until a token is available."""
        if self.tokens >= 1:
            return 0
        tokens_needed = 1 - self.tokens
        return tokens_needed / self.refill_rate


class RateLimitConfig:
    """Rate limiting configuration."""

    def __init__(self):
        self.enabled = os.environ.get("WTC_RATE_LIMIT_ENABLED", "true").lower() == "true"
        self.requests_per_window = int(os.environ.get("WTC_RATE_LIMIT_REQUESTS", "100"))
        self.window_seconds = int(os.environ.get("WTC_RATE_LIMIT_WINDOW", "60"))
        self.burst = int(os.environ.get("WTC_RATE_LIMIT_BURST", "20"))

        # Calculate refill rate
        self.refill_rate = self.requests_per_window / self.window_seconds

        # Endpoints with stricter limits
        self.strict_endpoints = {
            "/api/v1/auth/login": (5, 60),      # 5 per minute
            "/api/v1/auth/token": (5, 60),      # 5 per minute
            "/api/v1/users": (10, 60),          # 10 per minute for user management
        }

        # Endpoints with relaxed limits (high-frequency polling)
        self.relaxed_endpoints = {
            "/api/v1/rtus": (300, 60),          # 5 per second allowed
            "/api/v1/alarms": (300, 60),        # 5 per second allowed
            "/health": (600, 60),               # 10 per second allowed
        }

        # Endpoints exempt from rate limiting
        self.exempt_endpoints = {
            "/api/v1/ws",                       # WebSocket (handled differently)
            "/api/docs",                        # Documentation
            "/api/redoc",
            "/api/openapi.json",
        }


class RateLimiter:
    """
    In-memory rate limiter using token bucket algorithm.

    For production with multiple API instances, replace with Redis-backed limiter.
    """

    def __init__(self, config: RateLimitConfig | None = None):
        self.config = config or RateLimitConfig()
        self._buckets: dict[str, TokenBucket] = {}
        self._cleanup_interval = 300  # 5 minutes
        self._last_cleanup = time.monotonic()

    def _get_client_id(self, request: Request) -> str:
        """
        Get client identifier for rate limiting.
        Uses X-Forwarded-For if behind proxy, otherwise client IP.
        """
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take first IP (original client)
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"

        return client_ip

    def _get_bucket_key(self, client_id: str, path: str) -> str:
        """Get bucket key for client and path combination."""
        # Use path prefix for endpoint-specific limits
        for prefix in self.config.strict_endpoints:
            if path.startswith(prefix):
                return f"{client_id}:{prefix}"
        for prefix in self.config.relaxed_endpoints:
            if path.startswith(prefix):
                return f"{client_id}:{prefix}"
        return f"{client_id}:default"

    def _get_limits(self, path: str) -> tuple[int, int]:
        """Get (requests, window) for path."""
        for prefix, limits in self.config.strict_endpoints.items():
            if path.startswith(prefix):
                return limits
        for prefix, limits in self.config.relaxed_endpoints.items():
            if path.startswith(prefix):
                return limits
        return (self.config.requests_per_window, self.config.window_seconds)

    def _get_or_create_bucket(self, key: str, path: str) -> TokenBucket:
        """Get or create a token bucket for the key."""
        if key not in self._buckets:
            requests, window = self._get_limits(path)
            capacity = requests + self.config.burst
            refill_rate = requests / window
            self._buckets[key] = TokenBucket(
                capacity=capacity,
                tokens=capacity,
                refill_rate=refill_rate
            )
        return self._buckets[key]

    def _cleanup_old_buckets(self) -> None:
        """Remove old buckets to prevent memory growth."""
        now = time.monotonic()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = now
        # Remove buckets that haven't been used in 10 minutes
        stale_threshold = now - 600
        stale_keys = [
            key for key, bucket in self._buckets.items()
            if bucket.last_refill < stale_threshold
        ]
        for key in stale_keys:
            del self._buckets[key]

        if stale_keys:
            logger.debug(f"Cleaned up {len(stale_keys)} stale rate limit buckets")

    def is_exempt(self, path: str) -> bool:
        """Check if path is exempt from rate limiting."""
        return any(path.startswith(prefix) for prefix in self.config.exempt_endpoints)

    def check_rate_limit(self, request: Request) -> tuple[bool, float, dict]:
        """
        Check if request should be rate limited.

        Returns:
            (allowed, retry_after, headers)
        """
        if not self.config.enabled:
            return True, 0, {}

        path = request.url.path

        if self.is_exempt(path):
            return True, 0, {}

        client_id = self._get_client_id(request)
        bucket_key = self._get_bucket_key(client_id, path)
        bucket = self._get_or_create_bucket(bucket_key, path)

        # Periodic cleanup
        self._cleanup_old_buckets()

        # Try to consume a token
        allowed = bucket.consume()
        retry_after = bucket.retry_after

        # Build rate limit headers
        requests, window = self._get_limits(path)
        headers = {
            "X-RateLimit-Limit": str(requests),
            "X-RateLimit-Remaining": str(int(bucket.tokens)),
            "X-RateLimit-Reset": str(int(time.time() + window)),
        }

        if not allowed:
            headers["Retry-After"] = str(int(retry_after) + 1)
            logger.warning(
                f"Rate limit exceeded for {client_id} on {path}",
                extra={"client_id": client_id, "path": path}
            )

        return allowed, retry_after, headers


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""

    def __init__(self, app, limiter: RateLimiter | None = None):
        super().__init__(app)
        self.limiter = limiter or RateLimiter()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        allowed, retry_after, headers = self.limiter.check_rate_limit(request)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many requests",
                        "operator_message": f"Please wait {int(retry_after) + 1} seconds before retrying.",
                        "retry_after": int(retry_after) + 1,
                    }
                },
                headers=headers
            )

        response = await call_next(request)

        # Add rate limit headers to successful responses
        for key, value in headers.items():
            response.headers[key] = value

        return response


# Singleton instance for use across the application
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset rate limiter (useful for testing)."""
    global _rate_limiter
    _rate_limiter = None
