import re
from config import Config

_demo_mode: bool = Config.DEMO_MODE_DEFAULT


def set_demo_mode(enabled: bool):
    global _demo_mode
    _demo_mode = enabled


def is_demo_mode() -> bool:
    return _demo_mode


def check_sql_permission(sql: str, role: str) -> dict:
    sql_upper = re.sub(r'--.*', '', sql.strip().upper())
    sql_upper = re.sub(r'/\*.*?\*/', '', sql_upper, flags=re.DOTALL)
    words     = sql_upper.split()
    operation = words[0] if words else ""

    dangerous = operation in Config.DANGEROUS_OPERATIONS

    base = {
        "allowed": False, "needs_confirm": False,
        "operation": operation, "message": "", "demo_mode": _demo_mode,
    }

    if _demo_mode and operation not in ("SELECT", "EXPLAIN", "PRAGMA", "WITH"):
        base["message"] = (
            f"🔒 Demo Mode Aktif — Operasi '{operation}' diblok. "
            "Hanya SELECT yang diizinkan saat presentasi."
        )
        return base

    if role == "user":
        if operation not in ("SELECT", "EXPLAIN", "WITH", "PRAGMA"):
            base["message"] = (
                f"Akses ditolak! Role 'user' hanya boleh SELECT. "
                f"Operasi '{operation}' tidak diizinkan."
            )
        else:
            base.update({"allowed": True, "message": "Query SELECT diizinkan."})
        return base

    if role == "admin":
        if dangerous:
            base.update({
                "allowed": True, "needs_confirm": True,
                "message": (
                    f"Operasi '{operation}' dapat mengubah/menghapus data. "
                    "Konfirmasi eksekusi diperlukan."
                ),
            })
        else:
            base.update({"allowed": True, "message": "Query diizinkan."})
        return base

    base["message"] = "Role tidak dikenal. Akses ditolak."
    return base


def validate_sql_syntax(sql: str) -> dict:
    """Validasi dasar: SQL harus diawali keyword yang valid."""
    sql_up = sql.strip().upper()
    if not sql_up:
        return {"valid": False, "error": "SQL kosong.", "operation": ""}

    valid_starts = {
        "SELECT", "INSERT", "UPDATE", "DELETE", "DROP",
        "CREATE", "ALTER", "EXPLAIN", "WITH", "PRAGMA",
    }
    first = sql_up.split()[0] if sql_up.split() else ""

    if first not in valid_starts:
        return {
            "valid": False,
            "error": f"SQL tidak valid. Keyword pertama: '{first}'",
            "operation": first,
        }

    cleaned = re.sub(r"'[^']*'", "''", sql)
    semis   = [i for i, c in enumerate(cleaned) if c == ";"]
    if semis and semis[-1] < len(cleaned.rstrip()) - 1:
        return {
            "valid": False,
            "error": "Multiple SQL statements tidak diizinkan.",
            "operation": first,
        }

    return {"valid": True, "error": None, "operation": first}
