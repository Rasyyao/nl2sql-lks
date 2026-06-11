import re
import sqlite3
import time
from config import Config


class OptimizationRule:
    """Satu aturan optimasi SQL."""
    def __init__(self, rule_id: str, name: str, penalty: int,
                 category: str, description: str, suggestion: str):
        self.rule_id     = rule_id
        self.name        = name
        self.penalty     = penalty
        self.category    = category    # structural | performance | correctness | best_practice
        self.description = description
        self.suggestion  = suggestion 


RULES = [
    OptimizationRule(
        "S01", "SELECT *", penalty=10,
        category="structural",
        description="Menggunakan SELECT * mengambil semua kolom termasuk yang tidak dibutuhkan.",
        suggestion="Sebutkan kolom secara eksplisit: SELECT s.nama, s.nis, ... "
                   "Ini lebih efisien dan kode lebih mudah dipahami."
    ),
    OptimizationRule(
        "S02", "Implicit JOIN", penalty=15,
        category="structural",
        description="Menggunakan implicit JOIN (FROM a, b WHERE a.id = b.x) — gaya lama dan tidak direkomendasikan.",
        suggestion="Gunakan explicit JOIN: FROM siswa s JOIN kelas k ON s.kelas_id = k.id"
    ),
    OptimizationRule(
        "S03", "Tanpa alias tabel", penalty=5,
        category="structural",
        description="Query multi-tabel tanpa alias tabel membuat kode sulit dibaca.",
        suggestion="Tambahkan alias: FROM siswa s JOIN kelas k ON s.kelas_id = k.id"
    ),
    OptimizationRule(
        "S04", "Multiple statements", penalty=30,
        category="structural",
        description="Ditemukan multiple SQL statements dalam satu query (potensi SQL injection).",
        suggestion="Pisahkan menjadi satu statement per query."
    ),

    # ── PERFORMANCE (pola yang berpotensi lambat) ─────────────
    OptimizationRule(
        "P01", "LIKE dengan leading wildcard", penalty=10,
        category="performance",
        description="LIKE '%...%' atau LIKE '%...' tidak bisa menggunakan index — full table scan.",
        suggestion="Jika memungkinkan, gunakan LIKE 'nilai%' (wildcard di akhir saja) "
                   "atau full-text search."
    ),
    OptimizationRule(
        "P02", "Subquery IN vs JOIN", penalty=8,
        category="performance",
        description="WHERE x IN (SELECT ...) sering lebih lambat dari JOIN di SQLite.",
        suggestion="Pertimbangkan: FROM tabel_a JOIN tabel_b ON ... "
                   "Atau gunakan EXISTS: WHERE EXISTS (SELECT 1 FROM ...)"
    ),
    OptimizationRule(
        "P03", "DISTINCT tanpa kebutuhan", penalty=5,
        category="performance",
        description="DISTINCT menambah overhead sorting — pastikan benar-benar dibutuhkan.",
        suggestion="Cek apakah duplikat bisa dihindari dari desain JOIN yang benar, "
                   "atau ganti dengan GROUP BY jika perlu agregasi."
    ),
    OptimizationRule(
        "P04", "Fungsi pada kolom WHERE", penalty=8,
        category="performance",
        description="Menggunakan fungsi pada kolom di WHERE (misal: UPPER(nama) = 'X') "
                    "mencegah penggunaan index.",
        suggestion="Simpan data dalam format yang konsisten dan query tanpa transformasi: "
                   "WHERE nama = 'Andi' bukan WHERE UPPER(nama) = 'ANDI'"
    ),
    OptimizationRule(
        "P05", "ORDER BY tanpa LIMIT pada data besar", penalty=5,
        category="performance",
        description="ORDER BY tanpa LIMIT memaksa sort semua baris — bisa lambat pada data besar.",
        suggestion="Tambahkan LIMIT jika hanya butuh top-N hasil: ORDER BY nilai DESC LIMIT 10"
    ),

    # ── CORRECTNESS (apakah SQL sesuai maksud) ────────────────
    OptimizationRule(
        "C01", "HAVING tanpa GROUP BY", penalty=20,
        category="correctness",
        description="HAVING digunakan tanpa GROUP BY — logically incorrect.",
        suggestion="HAVING harus selalu berpasangan dengan GROUP BY. "
                   "Gunakan WHERE jika tidak ada agregasi."
    ),
    OptimizationRule(
        "C02", "COUNT(*) vs COUNT(kolom)", penalty=3,
        category="correctness",
        description="COUNT(kolom) tidak menghitung NULL, COUNT(*) menghitung semua baris. "
                    "Pastikan intent sesuai.",
        suggestion="Gunakan COUNT(*) untuk total baris, COUNT(kolom) jika ingin exclude NULL."
    ),
    OptimizationRule(
        "C03", "GROUP BY tidak konsisten dengan SELECT", penalty=12,
        category="correctness",
        description="Kolom di SELECT yang bukan fungsi agregat harus ada di GROUP BY.",
        suggestion="Pastikan semua kolom non-agregat di SELECT masuk ke GROUP BY: "
                   "SELECT s.nama, AVG(n.nilai) FROM ... GROUP BY s.id, s.nama"
    ),

    # ── BEST PRACTICE ─────────────────────────────────────────
    OptimizationRule(
        "B01", "Nama tabel tanpa alias di query kompleks", penalty=5,
        category="best_practice",
        description="Query dengan 3+ tabel sebaiknya selalu menggunakan alias untuk keterbacaan.",
        suggestion="Konsistenkan alias: s=siswa, k=kelas, m=mapel, n=nilai_mapel"
    ),
    OptimizationRule(
        "B02", "Hardcode nilai tanpa komentar", penalty=2,
        category="best_practice",
        description="Nilai magic number (misal: WHERE status = 1) tanpa konteks bisa membingungkan.",
        suggestion="Gunakan nilai yang self-explanatory atau tambahkan alias: "
                   "WHERE gender = 'L' -- Laki-laki"
    ),
    OptimizationRule(
        "B03", "Subquery correlated tidak perlu", penalty=8,
        category="best_practice",
        description="Subquery correlated dieksekusi sekali per baris outer query — sangat lambat.",
        suggestion="Pertimbangkan rewrite dengan JOIN atau subquery non-correlated."
    ),
]


def evaluate_sql(sql: str, question: str = "", explain_result: dict = None) -> dict:
    sql_up    = sql.strip().upper()
    sql_clean = re.sub(r"'[^']*'", "''", sql)
    findings  = []
    total_penalty = 0

    for rule in RULES:
        triggered, evidence = _check_rule(rule.rule_id, sql, sql_up, sql_clean)
        if triggered:
            findings.append({
                "rule_id":     rule.rule_id,
                "name":        rule.name,
                "category":    rule.category,
                "penalty":     rule.penalty,
                "description": rule.description,
                "suggestion":  rule.suggestion,
                "evidence":    evidence,
            })
            total_penalty += rule.penalty

    score = max(0, 100 - total_penalty)
    grade = _score_to_grade(score)

    cat_penalties = {"structural": 0, "performance": 0, "correctness": 0, "best_practice": 0}
    cat_max       = {"structural": 60, "performance": 36, "correctness": 35, "best_practice": 15}
    for f in findings:
        cat_penalties[f["category"]] += f["penalty"]

    categories = {
        cat: {
            "score":   max(0, cat_max[cat] - cat_penalties[cat]),
            "max":     cat_max[cat],
            "penalty": cat_penalties[cat],
            "pct":     round(max(0, cat_max[cat] - cat_penalties[cat]) / cat_max[cat] * 100),
        }
        for cat in cat_max
    }

    explain_info = _analyze_explain(explain_result)

    summary = _build_summary(score, grade, findings, explain_info)

    optimized = _suggest_optimized_sql(sql, findings)

    return {
        "score":         score,
        "grade":         grade,
        "findings":      findings,
        "categories":    categories,
        "explain_info":  explain_info,
        "optimized_sql": optimized,
        "summary":       summary,
        "sql_evaluated": sql,
        "timestamp":     time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def _check_rule(rule_id: str, sql: str, sql_up: str, sql_clean: str) -> tuple[bool, str]:

    if rule_id == "S01":
        if re.search(r'\bSELECT\s+\*', sql_up):
            return True, "Ditemukan SELECT *"
        return False, ""

    if rule_id == "S02":
        from_clause = re.search(r'\bFROM\s+([\w\s,]+?)(?:\bWHERE\b|\bGROUP\b|\bORDER\b|\bHAVING\b|\bLIMIT\b|$)', sql_up)
        if from_clause:
            tables = from_clause.group(1)
            if ',' in tables and 'JOIN' not in sql_up:
                return True, f"Implicit JOIN: FROM {from_clause.group(1).strip()[:50]}"
        return False, ""

    if rule_id == "S03":
        join_count = len(re.findall(r'\bJOIN\b', sql_up))
        if join_count >= 2:
            alias_count = len(re.findall(r'\b(?:FROM|JOIN)\s+\w+\s+\w\b', sql_up))
            if alias_count < join_count:
                return True, f"{join_count} JOIN tapi alias tidak konsisten"
        return False, ""

    if rule_id == "S04":
        semis = [i for i, c in enumerate(sql_clean) if c == ';']
        if semis and semis[-1] < len(sql_clean.rstrip()) - 1:
            return True, "Multiple statements ditemukan"
        return False, ""

    if rule_id == "P01":
        likes = re.findall(r"LIKE\s+'%[^']*'", sql_up)
        if likes:
            return True, f"Leading wildcard: {likes[0][:30]}"
        return False, ""

    if rule_id == "P02":
        if re.search(r'\bIN\s*\(\s*SELECT\b', sql_up):
            # Hanya flag jika bukan subquery sederhana yang tidak bisa diJOIN
            return True, "WHERE ... IN (SELECT ...) — pertimbangkan JOIN"
        return False, ""

    if rule_id == "P03":
        if re.search(r'\bSELECT\s+DISTINCT\b', sql_up):
            return True, "DISTINCT ditemukan"
        return False, ""

    if rule_id == "P04":
        func_where = re.search(
            r'\bWHERE\b.*?\b(UPPER|LOWER|TRIM|LENGTH|DATE|STRFTIME)\s*\(', sql_up
        )
        if func_where:
            return True, f"Fungsi {func_where.group(1)} pada kolom WHERE"
        return False, ""

    if rule_id == "P05":
        has_order = bool(re.search(r'\bORDER\s+BY\b', sql_up))
        has_limit = bool(re.search(r'\bLIMIT\b', sql_up))
        has_agg   = bool(re.search(r'\b(COUNT|SUM|AVG|MAX|MIN)\b', sql_up))
        # Flag hanya jika ORDER BY ada, LIMIT tidak ada, dan bukan query agregasi sederhana
        if has_order and not has_limit and not has_agg:
            return True, "ORDER BY tanpa LIMIT"
        return False, ""

    if rule_id == "C01":
        has_having = bool(re.search(r'\bHAVING\b', sql_up))
        has_group  = bool(re.search(r'\bGROUP\s+BY\b', sql_up))
        if has_having and not has_group:
            return True, "HAVING tanpa GROUP BY"
        return False, ""

    if rule_id == "C02":
        count_star = len(re.findall(r'\bCOUNT\s*\(\s*\*\s*\)', sql_up))
        count_col  = len(re.findall(r'\bCOUNT\s*\(\s*\w', sql_up))
        if count_star > 0 and count_col > 0:
            return True, "Campuran COUNT(*) dan COUNT(kolom)"
        return False, ""

    if rule_id == "C03":
        if not re.search(r'\bGROUP\s+BY\b', sql_up):
            return False, ""
        select_part = re.search(r'\bSELECT\b(.*?)\bFROM\b', sql_up, re.DOTALL)
        if select_part:
            cols = select_part.group(1)
            has_agg = bool(re.search(r'\b(AVG|SUM|COUNT|MAX|MIN)\s*\(', cols))
            group_part = re.search(
                r'\bGROUP\s+BY\s+(.*?)(?:\bHAVING\b|\bORDER\b|\bLIMIT\b|$)',
                sql_up, re.DOTALL
            )
            if has_agg and group_part:
                group_cols = group_part.group(1).strip()

                has_pk_group = bool(re.search(r'\b\w*\.?ID\b', group_cols))
                if not has_pk_group:
                    # Benar-benar tidak ada primary key di GROUP BY
                    non_agg_cols = re.findall(r'\b\w+\.\w+\b', cols)
                    non_agg_cols = [c for c in non_agg_cols
                                    if not re.search(r'\b(AVG|SUM|COUNT|MAX|MIN)\s*\(' + re.escape(c), cols)]
                    if non_agg_cols:
                        return True, f"GROUP BY tanpa primary key, SELECT berisi: {non_agg_cols[:2]}"
        return False, ""

    if rule_id == "B01":
        join_count = len(re.findall(r'\bJOIN\b', sql_up))
        if join_count >= 2:
            # Cek apakah ada tabel tanpa alias
            tables_no_alias = re.findall(r'\b(?:FROM|JOIN)\s+(\w+)(?:\s+(?:WHERE|ON|JOIN|GROUP|ORDER|HAVING|LIMIT|\())|\s*$', sql_up)
            if tables_no_alias:
                return True, f"Tabel tanpa alias: {', '.join(set(tables_no_alias))[:40]}"
        return False, ""

    if rule_id == "B02":
        # Flag WHERE dengan angka saja tanpa konteks jelas
        magic = re.findall(r'\bWHERE\b.*?\b(\d+)\b', sql_up)
        if magic and not any(kw in sql_up for kw in ['LIMIT', 'OFFSET']):
            return True, f"Nilai numerik dalam WHERE: {magic[:2]}"
        return False, ""

    if rule_id == "B03":
        # Pattern: subquery yang referensi alias dari outer query
        if re.search(r'\bEXISTS\s*\(\s*SELECT', sql_up):
            return True, "Correlated subquery dengan EXISTS"
        return False, ""

    return False, ""


def _score_to_grade(score: int) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"


def _analyze_explain(explain_result: dict | None) -> dict:
    if not explain_result or not explain_result.get("success"):
        return {"available": False, "scan_types": [], "warnings": []}

    rows     = explain_result.get("rows", [])
    text     = " ".join(str(r) for r in rows).upper()
    warnings = []
    scans    = []

    if "SCAN" in text and "SEARCH" not in text:
        scans.append("FULL TABLE SCAN")
        warnings.append("⚠️ Full table scan terdeteksi — pertimbangkan menambah index atau filter lebih spesifik")
    elif "SEARCH" in text:
        scans.append("INDEX SEARCH")
    if "TEMP B-TREE" in text:
        scans.append("TEMP B-TREE")
        warnings.append("⚠️ Temporary B-tree untuk ORDER BY/GROUP BY — bisa lambat pada data besar")
    if "CORRELATED" in text:
        warnings.append("⚠️ Correlated subquery terdeteksi di EXPLAIN")
    if not rows:
        scans.append("N/A")

    return {
        "available":  True,
        "scan_types": scans,
        "warnings":   warnings,
        "raw":        [str(r) for r in rows[:5]],
    }


def _build_summary(score: int, grade: str, findings: list, explain_info: dict) -> str:
    if score == 100:
        return "✅ Query optimal! Tidak ada masalah yang ditemukan."

    parts = [f"Grade {grade} ({score}/100)."]

    critical = [f for f in findings if f["penalty"] >= 15]
    moderate = [f for f in findings if 8 <= f["penalty"] < 15]
    minor    = [f for f in findings if f["penalty"] < 8]

    if critical:
        parts.append(f"🔴 Masalah kritis: {', '.join(f['name'] for f in critical)}.")
    if moderate:
        parts.append(f"🟡 Perlu perhatian: {', '.join(f['name'] for f in moderate)}.")
    if minor:
        parts.append(f"🟢 Saran minor: {len(minor)} item.")

    if explain_info.get("warnings"):
        parts.append(explain_info["warnings"][0])

    return " ".join(parts)


def _suggest_optimized_sql(sql: str, findings: list) -> str | None:

    optimized = sql
    changed   = False

    rule_ids = {f["rule_id"] for f in findings}

    if not changed:
        return None
    return optimized


def setup_optimization_table():
    conn = sqlite3.connect(Config.AUDIT_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_optimization_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT,
            question     TEXT,
            sql_query    TEXT,
            score        INTEGER,
            grade        TEXT,
            findings_json TEXT,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_optimization_result(username: str, question: str, sql: str, result: dict):
    import json
    try:
        conn = sqlite3.connect(Config.AUDIT_DB_PATH)
        conn.execute(
            "INSERT INTO query_optimization_log "
            "(username, question, sql_query, score, grade, findings_json) "
            "VALUES (?,?,?,?,?,?)",
            (username, question, sql, result["score"], result["grade"],
             json.dumps(result["findings"], ensure_ascii=False))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[OPT] Gagal simpan: {e}")


def get_optimization_stats() -> dict:
    try:
        conn = sqlite3.connect(Config.AUDIT_DB_PATH)
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            "SELECT score, grade FROM query_optimization_log ORDER BY created_at DESC LIMIT 100"
        ).fetchall()

        if not rows:
            return {"total_evaluated": 0, "avg_score": 0, "grade_dist": {},
                    "trend": "Belum ada data"}

        scores     = [r["score"] for r in rows]
        grade_dist = {}
        for r in rows:
            grade_dist[r["grade"]] = grade_dist.get(r["grade"], 0) + 1

        avg_score = round(sum(scores) / len(scores), 1)

        trend = "Stabil"
        if len(scores) >= 20:
            recent = sum(scores[:10]) / 10
            older  = sum(scores[10:20]) / 10
            if recent > older + 3:
                trend = "↗ Meningkat"
            elif recent < older - 3:
                trend = "↘ Menurun"

        conn.close()
        return {
            "total_evaluated": len(rows),
            "avg_score":       avg_score,
            "grade_dist":      grade_dist,
            "trend":           trend,
        }
    except Exception:
        return {"total_evaluated": 0, "avg_score": 0, "grade_dist": {}, "trend": "Error"}


def get_optimization_history(limit: int = 20) -> list:
    import json
    try:
        conn = sqlite3.connect(Config.AUDIT_DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, username, question, sql_query, score, grade, created_at "
            "FROM query_optimization_log ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []
