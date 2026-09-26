"""Unit tests for backend.cache module."""
from decimal import Decimal
from unittest.mock import MagicMock, patch
import zlib
import simplejson
import pytest

from backend.cache import (
    _make_key,
    cache_get,
    cache_set,
    cached_response,
    invalidate,
    redis_available,
    reset_redis,
)


def test_make_key_deterministic():
    """Cache key generation must be deterministic regardless of dict order."""
    params1 = {"krs": "0000123456", "status": "developer_candidate", "limit": 25}
    params2 = {"limit": 25, "status": "developer_candidate", "krs": "0000123456"}
    key1 = _make_key("profiles", params1)
    key2 = _make_key("profiles", params2)
    assert key1 == key2
    assert key1.startswith("cl:profiles:")


def test_make_key_different_params():
    """Different parameters must produce different keys."""
    key1 = _make_key("profiles", {"q": "Budimex"})
    key2 = _make_key("profiles", {"q": "Dom Development"})
    assert key1 != key2


def test_cached_response_when_redis_unavailable():
    """When Redis is not available, compute function is called and returns (result, False)."""
    with patch("backend.cache.get_redis", return_value=None):
        called = False

        def compute():
            nonlocal called
            called = True
            return {"status": "ok", "value": 42}

        result, from_cache = cached_response("test", {"a": 1}, compute)
        assert called is True
        assert result == {"status": "ok", "value": 42}
        assert from_cache is False


def test_cache_miss_then_hit_with_mock_redis():
    """Simulate cache miss followed by cache hit."""
    fake_storage = {}
    mock_redis = MagicMock()

    def fake_get(key):
        return fake_storage.get(key)

    def fake_set(key, val, ex=None):
        fake_storage[key] = val

    mock_redis.get.side_effect = fake_get
    mock_redis.set.side_effect = fake_set

    with patch("backend.cache.get_redis", return_value=mock_redis):
        call_count = 0

        def compute():
            nonlocal call_count
            call_count += 1
            return {"count": 100, "revenue": Decimal("12345.67")}

        # 1st call: MISS
        res1, from_cache1 = cached_response("test", {"id": "x"}, compute)
        assert call_count == 1
        assert from_cache1 is False
        assert res1["count"] == 100
        assert res1["revenue"] == Decimal("12345.67")

        # 2nd call: HIT (compute must NOT be called again)
        res2, from_cache2 = cached_response("test", {"id": "x"}, compute)
        assert call_count == 1
        assert from_cache2 is True
        assert res2["count"] == 100
        # Cached payloads are decoded to ordinary JSON numbers so they can be
        # passed directly to Starlette's JSONResponse.
        assert res2["revenue"] == pytest.approx(12345.67)
        assert isinstance(res2["revenue"], float)


def test_corrupted_cache_fallback():
    """If cache contains invalid data, compute is re-run gracefully."""
    mock_redis = MagicMock()
    mock_redis.get.return_value = b"corrupted garbage that cannot be decompressed"

    with patch("backend.cache.get_redis", return_value=mock_redis):
        called = False

        def compute():
            nonlocal called
            called = True
            return {"recovered": True}

        result, from_cache = cached_response("test", {}, compute)
        assert called is True
        assert result == {"recovered": True}
        assert from_cache is False


def test_invalidate_pattern():
    """Invalidate deletes keys matching pattern."""
    mock_redis = MagicMock()
    mock_redis.scan_iter.return_value = [b"cl:profiles:abc", b"cl:profiles:def"]
    mock_redis.delete.return_value = 2

    with patch("backend.cache.get_redis", return_value=mock_redis):
        deleted = invalidate("cl:profiles:*")
        assert deleted == 2
        mock_redis.scan_iter.assert_called_once_with(match="cl:profiles:*", count=500)
        mock_redis.delete.assert_called_once_with(b"cl:profiles:abc", b"cl:profiles:def")


def test_redis_available():
    with patch("backend.cache.get_redis", return_value=MagicMock()):
        assert redis_available() is True
    with patch("backend.cache.get_redis", return_value=None):
        assert redis_available() is False
