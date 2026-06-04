"""
GeoIntel Caching Layer
======================
Simple in-memory TTL cache that works out of the box.
Optional Redis upgrade: set REDIS_URL env var to enable distributed caching.

Usage:
    from cache import cache_get, cache_set, cache_delete, cache_clear_prefix

    # Get cached value
    data = cache_get('crises:all')

    # Set with TTL (seconds)
    cache_set('crises:all', data, ttl=60)

    # Delete a key
    cache_delete('crises:all')

    # Clear all keys matching prefix (e.g. on data sync)
    cache_clear_prefix('crises:')
"""
import time
import json
import logging
import os
from threading import Lock

logger = logging.getLogger(__name__)

# ── In-memory cache store ─────────────────────────────────────────────────────
_cache = {}          # { key: (value, expires_at) }
_cache_lock = Lock()

# ── Optional Redis ─────────────────────────────────────────────────────────────
_redis_client = None
REDIS_URL = os.getenv('REDIS_URL')

if REDIS_URL:
    try:
        import redis
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
        _redis_client.ping()
        logger.info(f"Redis cache connected: {REDIS_URL}")
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}). Falling back to in-memory cache.")
        _redis_client = None
else:
    logger.info("No REDIS_URL set. Using in-memory cache.")


# ── Core cache functions ───────────────────────────────────────────────────────

def cache_get(key: str):
    """Return cached value or None if missing/expired."""
    if _redis_client:
        try:
            val = _redis_client.get(key)
            return json.loads(val) if val else None
        except Exception as e:
            logger.warning(f"Redis get error for '{key}': {e}")

    # In-memory fallback
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at and time.time() > expires_at:
            del _cache[key]
            return None
        return value


def cache_set(key: str, value, ttl: int = 60):
    """Cache value with TTL in seconds (0 = no expiry)."""
    if _redis_client:
        try:
            serialized = json.dumps(value, default=str)
            if ttl:
                _redis_client.setex(key, ttl, serialized)
            else:
                _redis_client.set(key, serialized)
            return
        except Exception as e:
            logger.warning(f"Redis set error for '{key}': {e}")

    # In-memory fallback
    expires_at = (time.time() + ttl) if ttl else None
    with _cache_lock:
        _cache[key] = (value, expires_at)


def cache_delete(key: str):
    """Delete a specific cache key."""
    if _redis_client:
        try:
            _redis_client.delete(key)
            return
        except Exception as e:
            logger.warning(f"Redis delete error for '{key}': {e}")

    with _cache_lock:
        _cache.pop(key, None)


def cache_clear_prefix(prefix: str):
    """Clear all keys starting with prefix. Call after data mutations."""
    if _redis_client:
        try:
            keys = _redis_client.keys(f"{prefix}*")
            if keys:
                _redis_client.delete(*keys)
            return
        except Exception as e:
            logger.warning(f"Redis clear_prefix error for '{prefix}': {e}")

    with _cache_lock:
        to_delete = [k for k in _cache if k.startswith(prefix)]
        for k in to_delete:
            del _cache[k]
    if to_delete:
        logger.info(f"Cache cleared {len(to_delete)} keys with prefix '{prefix}'")


def cache_stats() -> dict:
    """Return cache stats for the /api/health endpoint."""
    if _redis_client:
        try:
            info = _redis_client.info('memory')
            return {
                'backend': 'redis',
                'used_memory': info.get('used_memory_human', 'unknown'),
                'connected': True,
            }
        except Exception:
            pass

    with _cache_lock:
        total = len(_cache)
        expired = sum(
            1 for _, (_, exp) in _cache.items()
            if exp and time.time() > exp
        )
        return {
            'backend': 'memory',
            'total_keys': total,
            'expired_keys': expired,
            'live_keys': total - expired,
        }
