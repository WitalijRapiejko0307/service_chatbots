"""Middleware for request processing."""

import asyncio
import time
import uuid
import logging
from typing import Callable, Optional

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.utils.logging_config import is_secret_query_key, redact_secrets

logger = logging.getLogger(__name__)

# Platform webhooks share IPs; IP limiting would 429 production inbound.
RATE_LIMIT_EXEMPT_EXACT = frozenset({"/health", "/health/"})
RATE_LIMIT_EXEMPT_PREFIXES = (
    "/api/v1/telegram/webhook",
    "/api/v1/viber/webhook",
    "/api/v1/instagram/webhook",
    "/api/v1/tiktok/webhook",
)


def is_rate_limit_exempt(path: str) -> bool:
    """True for liveness and messenger webhook paths (prefix match)."""
    normalized = path.rstrip("/") or "/"
    if path in RATE_LIMIT_EXEMPT_EXACT or normalized in {"/health"}:
        return True
    return any(path.startswith(prefix) for prefix in RATE_LIMIT_EXEMPT_PREFIXES)


def safe_query_params_for_log(path: str, query_params) -> str:
    """Redact secret query values; omit the query string on OAuth callbacks."""
    if "/oauth/" in (path or ""):
        return ""
    items: list[tuple[str, str]] = []
    for key, value in query_params.multi_items():
        if is_secret_query_key(key):
            items.append((key, "***"))
        else:
            items.append((key, redact_secrets(str(value))))
    return "&".join(f"{k}={v}" for k, v in items)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID to all requests."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add request ID to request and response."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = str(process_time)

        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response."""
        request_id = getattr(request.state, "request_id", None)
        start_time = time.time()

        logger.info(
            f"Request: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": safe_query_params_for_log(
                    request.url.path, request.query_params
                ),
            },
        )

        response = await call_next(request)

        process_time = time.time() - start_time

        logger.info(
            f"Response: {request.method} {request.url.path} - {response.status_code}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time": process_time,
            },
        )

        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limit by IP (Redis incr+expire per minute, in-memory fallback).

    Messenger webhook paths and /health are exempt — platform shared IPs would
    otherwise 429 production. Admin/API keep the configured per-minute cap.
    """

    def __init__(self, app, requests_per_minute: int = 60):
        """Initialize rate limiter."""
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.request_counts: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    def _too_many_response(self, client_ip: str, path: str, request: Request) -> JSONResponse:
        logger.warning(
            "Rate limit exceeded for %s",
            client_ip,
            extra={
                "client_ip": client_ip,
                "path": path,
                "request_id": getattr(request.state, "request_id", None),
            },
        )
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please try again later.",
                    "details": {},
                    "request_id": getattr(request.state, "request_id", None),
                }
            },
        )

    async def _redis_allow(self, client_ip: str) -> Optional[bool]:
        """Return True/False if Redis handled the check, None to use in-memory."""
        try:
            from app.storage.redis import get_redis_client

            redis = get_redis_client()
            if not await redis.ping():
                return None
            minute = int(time.time() // 60)
            key = f"ratelimit:{client_ip}:{minute}"
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, 90)
            return count <= self.requests_per_minute
        except Exception:
            return None

    async def _memory_allow(self, client_ip: str) -> bool:
        current_time = time.time()
        async with self._lock:
            window = self.request_counts.get(client_ip, [])
            window = [t for t in window if current_time - t < 60]
            if len(window) >= self.requests_per_minute:
                self.request_counts[client_ip] = window
                return False
            window.append(current_time)
            self.request_counts[client_ip] = window
            return True

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check rate limit."""
        path = request.url.path
        if is_rate_limit_exempt(path):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        redis_result = await self._redis_allow(client_ip)
        if redis_result is False:
            return self._too_many_response(client_ip, path, request)
        if redis_result is True:
            return await call_next(request)

        if not await self._memory_allow(client_ip):
            return self._too_many_response(client_ip, path, request)

        return await call_next(request)
