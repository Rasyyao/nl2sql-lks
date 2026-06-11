import time
import sqlite3
from config import Config

_metrics = {
    "total_requests":         0,
    "successful_queries":     0,
    "failed_queries":         0,
    "blocked_queries":        0,
    "cache_hits":             0,
    "auto_repaired":          0,
    "total_sql_gen_ms":       0.0,
    "total_exec_ms":          0.0,
    "start_time":             time.time(),
}


class Timer:
    def __init__(self):
        self.elapsed_ms = 0.0

    def __enter__(self):
        self._start = time.perf_counter()
        return self

    def __exit__(self, *_):
        self.elapsed_ms = (time.perf_counter() - self._start) * 1000


def record_request(
    sql_gen_ms: float = 0,
    exec_ms:    float = 0,
    success:    bool  = True,
    blocked:    bool  = False,
    cache_hit:  bool  = False,
    auto_repaired: bool = False,
):
    _metrics["total_requests"] += 1
    if cache_hit:     _metrics["cache_hits"]    += 1
    if auto_repaired: _metrics["auto_repaired"] += 1
    if blocked:       _metrics["blocked_queries"] += 1
    elif success:     _metrics["successful_queries"] += 1
    else:             _metrics["failed_queries"] += 1

    _metrics["total_sql_gen_ms"] += sql_gen_ms
    _metrics["total_exec_ms"]    += exec_ms

    try:
        conn = sqlite3.connect(Config.AUDIT_DB_PATH)
        conn.execute(
            "INSERT INTO metrics_log (sql_gen_ms, exec_ms, success, blocked) VALUES (?,?,?,?)",
            (sql_gen_ms, exec_ms, int(success), int(blocked))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_metrics() -> dict:
    m     = _metrics.copy()
    total = max(m["total_requests"], 1)

    m["avg_sql_gen_ms"]   = round(m["total_sql_gen_ms"] / total, 1)
    m["avg_exec_ms"]      = round(m["total_exec_ms"]    / total, 1)
    m["error_rate_pct"]   = round(m["failed_queries"]   / total * 100, 1)
    m["success_rate_pct"] = round(m["successful_queries"] / total * 100, 1)
    m["cache_hit_rate"]   = round(m["cache_hits"]        / total * 100, 1)

    uptime  = time.time() - m["start_time"]
    m["uptime"] = f"{int(uptime//3600)}j {int((uptime%3600)//60)}m"

    return m
