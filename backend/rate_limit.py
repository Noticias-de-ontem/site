"""Small, dependency-light abuse controls for public API endpoints.

Redis/Valkey is used when REDIS_URL is configured so limits are shared by
multiple web instances and by the Celery worker.  Local memory is kept as a
development fallback; it is intentionally not treated as a distributed
security boundary.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass


logger = logging.getLogger(__name__)


def positive_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(1, value)


def trust_proxy_headers() -> bool:
    return os.environ.get("RATE_LIMIT_TRUST_PROXY_HEADERS", "").lower() in {
        "1",
        "true",
        "yes",
    }


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int
    remaining: int
    limit: int


class _RedisProvider:
    def __init__(self):
        self.url = os.environ.get("REDIS_URL", "").strip()
        self.client = None
        self.disabled_until = 0.0
        self._lock = threading.Lock()

    def get(self):
        if not self.url or time.monotonic() < self.disabled_until:
            return None
        with self._lock:
            if self.client is not None:
                return self.client
            try:
                import redis

                self.client = redis.Redis.from_url(
                    self.url,
                    decode_responses=True,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                )
                self.client.ping()
                return self.client
            except Exception as exc:  # pragma: no cover - depends on deployment
                self.disabled_until = time.monotonic() + 30
                logger.warning("Distributed rate limiting unavailable: %s", type(exc).__name__)
                self.client = None
                return None

    def mark_failed(self, exc):
        with self._lock:
            self.client = None
            self.disabled_until = time.monotonic() + 30
        logger.warning("Distributed rate limiting request failed: %s", type(exc).__name__)


class _MemoryRateLimiter:
    def __init__(self):
        self._buckets = {}
        self._lock = threading.Lock()

    def consume(self, key: str, limit: int, window_seconds: int) -> RateLimitDecision:
        now = time.time()
        bucket = int(now // window_seconds)
        bucket_key = f"{key}:{bucket}"
        expires_at = (bucket + 1) * window_seconds
        with self._lock:
            for stale_key, (_, stale_expiry) in list(self._buckets.items()):
                if stale_expiry <= now:
                    self._buckets.pop(stale_key, None)
            count, _ = self._buckets.get(bucket_key, (0, expires_at))
            count += 1
            self._buckets[bucket_key] = (count, expires_at)
            if len(self._buckets) > 10000:
                oldest = sorted(self._buckets.items(), key=lambda item: item[1][1])[:1000]
                for stale_key, _ in oldest:
                    self._buckets.pop(stale_key, None)
        retry_after = max(1, int(expires_at - now))
        return RateLimitDecision(
            allowed=count <= limit,
            retry_after=retry_after,
            remaining=max(0, limit - count),
            limit=limit,
        )


class _MemoryJobSlots:
    def __init__(self):
        self._slots = {}
        self._lock = threading.Lock()

    def reserve(self, job_id: str, limit: int, ttl_seconds: int) -> bool:
        now = time.time()
        with self._lock:
            for stale_job_id, expiry in list(self._slots.items()):
                if expiry <= now:
                    self._slots.pop(stale_job_id, None)
            if job_id in self._slots:
                return True
            if len(self._slots) >= limit:
                return False
            self._slots[job_id] = now + ttl_seconds
            return True

    def release(self, job_id: str):
        with self._lock:
            self._slots.pop(job_id, None)


_redis = _RedisProvider()
_memory_rate_limiter = _MemoryRateLimiter()
_memory_job_slots = _MemoryJobSlots()


def identity_key(identity: str) -> str:
    """Avoid putting raw client identifiers in Redis keys or logs."""

    return hashlib.sha256(str(identity or "unknown").encode("utf-8")).hexdigest()


def consume_rate_limit(scope: str, identity: str, limit: int, window_seconds: int) -> RateLimitDecision:
    limit = max(1, int(limit))
    window_seconds = max(1, int(window_seconds))
    now = time.time()
    bucket = int(now // window_seconds)
    redis_key = f"ndo:rate:{scope}:{identity_key(identity)}:{bucket}"
    redis_client = _redis.get()
    if redis_client is not None:
        try:
            pipe = redis_client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds + 2)
            count, _ = pipe.execute()
            expires_at = (bucket + 1) * window_seconds
            return RateLimitDecision(
                allowed=int(count) <= limit,
                retry_after=max(1, int(expires_at - now)),
                remaining=max(0, limit - int(count)),
                limit=limit,
            )
        except Exception as exc:  # pragma: no cover - depends on deployment
            _redis.mark_failed(exc)
    return _memory_rate_limiter.consume(
        f"{scope}:{identity_key(identity)}",
        limit,
        window_seconds,
    )


_RESERVE_SLOT_SCRIPT = """
local now = tonumber(ARGV[1])
local expires = now + tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now)
if redis.call('ZCARD', KEYS[1]) >= limit and redis.call('ZSCORE', KEYS[1], ARGV[4]) == false then
  return 0
end
redis.call('ZADD', KEYS[1], expires, ARGV[4])
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]) + 60)
return 1
"""


_RELEASE_SLOT_SCRIPT = """
redis.call('ZREM', KEYS[1], ARGV[1])
if redis.call('ZCARD', KEYS[1]) == 0 then
  redis.call('DEL', KEYS[1])
end
return 1
"""


def reserve_topic_job_slot(job_id: str, limit: int, ttl_seconds: int) -> bool:
    limit = max(1, int(limit))
    ttl_seconds = max(60, int(ttl_seconds))
    redis_client = _redis.get()
    if redis_client is not None:
        try:
            result = redis_client.eval(
                _RESERVE_SLOT_SCRIPT,
                1,
                "ndo:topic:active-jobs",
                time.time(),
                ttl_seconds,
                limit,
                str(job_id),
            )
            return bool(int(result))
        except Exception as exc:  # pragma: no cover - depends on deployment
            _redis.mark_failed(exc)
    return _memory_job_slots.reserve(str(job_id), limit, ttl_seconds)


def release_topic_job_slot(job_id: str):
    redis_client = _redis.get()
    if redis_client is not None:
        try:
            redis_client.eval(
                _RELEASE_SLOT_SCRIPT,
                1,
                "ndo:topic:active-jobs",
                str(job_id),
            )
        except Exception as exc:  # pragma: no cover - depends on deployment
            _redis.mark_failed(exc)
    _memory_job_slots.release(str(job_id))
