"""Redis caching layer with graceful degradation.

When Redis is unavailable the application falls back to direct computation
without caching. All public helpers silently return *None* on connection
errors so callers can use a simple ``if hit is None: compute()`` pattern.
"""
from __future__ import annotations

import hashlib
import logging
import os
from functools import wraps
from typing import Callable, TypeVar

import simplejson

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

_redis_client = None
_redis_checked = False


def redis_url() -> str:
    if url := os.environ.get("REDIS_URL"):
        return url
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.isfile(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("REDIS_URL="):
                        val = line.split("=", 1)[1].strip().strip('"\'')
                        if val:
                            return val
        except Exception:
            pass
    return "redis://127.0.0.1:6379/0"


def get_redis():
    """Return a lazy-initialised Redis client, or *None* when unavailable."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    try:
        import redis as _redis_lib

        client = _redis_lib.Redis.from_url(
            redis_url(),
            decode_responses=False,
            socket_connect_timeout=2,
            socket_timeout=2,
            protocol=2,
        )
        client.ping()
        _redis_client = client
        logger.info("Redis connected: %s", redis_url())
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — running without cache.", exc)
        _redis_client = None
    return _redis_client


def redis_available() -> bool:
    """Check whether a working Redis connection exists."""
    return get_redis() is not None


def reset_redis() -> None:
    """Force re-check on next access (useful after config changes or tests)."""
    global _redis_client, _redis_checked
    _redis_client = None
    _redis_checked = False


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

DEFAULT_TTL = int(os.environ.get("CACHE_TTL_SECONDS", "600"))


def _make_key(prefix: str, params: dict) -> str:
    """Build a deterministic cache key from endpoint prefix + query params."""
    canonical = simplejson.dumps(params, sort_keys=True, use_decimal=True)
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return f"cl:{prefix}:{digest}"


def cache_get(key: str) -> bytes | None:
    """Fetch raw bytes from cache. Returns *None* on miss or error."""
    client = get_redis()
    if client is None:
        return None
    try:
        return client.get(key)
    except Exception as exc:
        logger.debug("cache_get error for %s: %s", key, exc)
        return None


def cache_set(key: str, value: bytes, ttl: int = DEFAULT_TTL) -> None:
    """Store raw bytes in cache with a TTL. Silently ignores errors."""
    client = get_redis()
    if client is None:
        return
    try:
        client.set(key, value, ex=ttl)
    except Exception as exc:
        logger.debug("cache_set error for %s: %s", key, exc)


def invalidate(pattern: str = "cl:*") -> int:
    """Delete cache keys matching *pattern*. Returns count of deleted keys."""
    client = get_redis()
    if client is None:
        return 0
    try:
        keys = list(client.scan_iter(match=pattern, count=500))
        if keys:
            return client.delete(*keys)
        return 0
    except Exception as exc:
        logger.debug("invalidate error: %s", exc)
        return 0


def cached_response(prefix: str, params: dict, compute: Callable[[], T],
                     ttl: int = DEFAULT_TTL) -> tuple[T, bool]:
    """Return ``(result, from_cache)`` using cache-aside pattern.

    *compute* is called only on cache miss. The result is serialised as JSON
    via simplejson (Decimal-safe) and compressed with zlib for storage.
    """
    import zlib

    key = _make_key(prefix, params)

    # Try cache first
    raw = cache_get(key)
    if raw is not None:
        try:
            # API payloads must remain compatible with Starlette's standard
            # JSON encoder.  ``use_decimal=True`` turned every cached float
            # into Decimal, so the first request worked but an identical cache
            # hit failed while creating JSONResponse.
            data = simplejson.loads(zlib.decompress(raw), use_decimal=False)
            return data, True
        except Exception:
            pass  # corrupted entry — recompute

    # Cache miss — compute fresh value
    result = compute()

    # Store in cache (best-effort)
    try:
        blob = zlib.compress(
            simplejson.dumps(result, sort_keys=True, use_decimal=True).encode(),
            level=3,
        )
        cache_set(key, blob, ttl)
    except Exception as exc:
        logger.debug("Failed to cache result for %s: %s", key, exc)

    return result, False
