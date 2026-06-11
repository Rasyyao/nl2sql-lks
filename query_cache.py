import hashlib
import time
from config import Config

_cache: dict = {}
TTL = Config.QUERY_CACHE_TTL


def _key(sql: str) -> str:
    return hashlib.md5(sql.strip().upper().encode()).hexdigest()


def get_cached_result(sql: str) -> dict | None:
    entry = _cache.get(_key(sql))
    if not entry:
        return None
    if time.time() - entry["ts"] > TTL:
        del _cache[_key(sql)]
        return None
    return entry["result"]


def set_cached_result(sql: str, result: dict):
    if sql.strip().upper().startswith("SELECT"):
        _cache[_key(sql)] = {"result": result, "ts": time.time()}


def invalidate_cache():
    global _cache
    _cache = {}


def get_cache_stats() -> dict:
    now    = time.time()
    active = sum(1 for e in _cache.values() if now - e["ts"] <= TTL)
    return {
        "total_entries":  len(_cache),
        "active_entries": active,
        "ttl_seconds":    TTL,
    }
