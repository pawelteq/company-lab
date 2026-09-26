"""Rate limiting middleware and logic with Redis sliding-window and in-memory fallback.

Protects /api/ endpoints from excessive requests and denial-of-service attempts.
Returns HTTP 429 Too Many Requests when the limit is exceeded.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from collections import defaultdict
from typing import Tuple

from fastapi import Request
from fastapi.responses import JSONResponse

from backend.cache import get_redis

logger = logging.getLogger(__name__)

DEFAULT_RATE_LIMIT = 120
WINDOW_SECONDS = 60

# In-memory storage for fallback when Redis is offline
# Structure: {ip: [timestamp1, timestamp2, ...]}
_in_memory_records: dict[str, list[float]] = defaultdict(list)
_last_cleanup = 0.0


def get_rate_limit() -> int:
    """Return configured rate limit per minute from environment or default."""
    try:
        return int(os.environ.get("RATE_LIMIT_PER_MINUTE", str(DEFAULT_RATE_LIMIT)))
    except ValueError:
        return DEFAULT_RATE_LIMIT


def get_client_ip(request: Request) -> str:
    """Extract client IP respecting X-Forwarded-For and X-Real-IP headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For can be a comma-separated list; first one is the original client
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


def check_rate_limit(ip: str, limit: int | None = None) -> Tuple[bool, int, int]:
    """Check if the given IP exceeded the sliding-window rate limit.

    Returns:
        (allowed: bool, remaining: int, retry_after: int)
    """
    if limit is None:
        limit = get_rate_limit()

    now = time.time()
    cutoff = now - WINDOW_SECONDS

    # 1. Try Redis sliding window (atomic, distributed across workers)
    redis = get_redis()
    if redis is not None:
        try:
            key = f"cl:rate:{ip}"
            member = f"{now}:{uuid.uuid4().hex[:6]}"
            pipe = redis.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zcard(key)
            pipe.zrange(key, 0, 0, withscores=True)
            results = pipe.execute()

            count = results[1]
            oldest = results[2]
            if oldest:
                oldest_score = oldest[0][1]
                retry_after = max(1, int(oldest_score + WINDOW_SECONDS - now))
            else:
                retry_after = WINDOW_SECONDS

            if count >= limit:
                return False, 0, retry_after

            # Within limit: record request and update TTL
            pipe = redis.pipeline()
            pipe.zadd(key, {member: now})
            pipe.expire(key, WINDOW_SECONDS + 5)
            pipe.execute()

            remaining = max(0, limit - (count + 1))
            return True, remaining, retry_after
        except Exception as exc:
            logger.debug("Redis rate-limit error, falling back to in-memory: %s", exc)

    # 2. In-memory sliding window fallback
    global _last_cleanup
    if now - _last_cleanup > 30:
        for k in list(_in_memory_records.keys()):
            _in_memory_records[k] = [t for t in _in_memory_records[k] if t > cutoff]
            if not _in_memory_records[k]:
                _in_memory_records.pop(k, None)
        _last_cleanup = now

    timestamps = [t for t in _in_memory_records[ip] if t > cutoff]
    retry_after = max(1, int(timestamps[0] + WINDOW_SECONDS - now)) if timestamps else WINDOW_SECONDS

    if len(timestamps) >= limit:
        _in_memory_records[ip] = timestamps
        return False, 0, retry_after

    timestamps.append(now)
    _in_memory_records[ip] = timestamps
    remaining = max(0, limit - len(timestamps))
    return True, remaining, retry_after


def reset_rate_limits() -> None:
    """Clear both Redis and in-memory rate limits (useful in tests)."""
    global _in_memory_records
    _in_memory_records.clear()
    redis = get_redis()
    if redis is not None:
        try:
            keys = list(redis.scan_iter(match="cl:rate:*", count=500))
            if keys:
                redis.delete(*keys)
        except Exception:
            pass
