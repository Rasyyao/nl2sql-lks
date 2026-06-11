import re
import os
from langchain_groq import ChatGroq
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from config import Config
from intent_classifier import intent_classifier
from schema_retrieval import schema_retriever
import numpy as np

_active_model: str = Config.DEFAULT_MODEL

def set_active_model(model_id: str) -> bool:
    global _active_model
    if model_id in Config.AVAILABLE_MODELS:
        _active_model = model_id
        return True
    return False

def get_active_model() -> str:
    return _active_model
    
def get_active_model_info() -> dict:
    return Config.AVAILABLE_MODELS.get(_active_model, {})

def _extract_token_usage(ai_msg) -> dict:
    """Normalize token usage from Groq or Anthropic AIMessage response_metadata."""
    meta = getattr(ai_msg, 'response_metadata', {}) or {}
    # Groq: {'token_usage': {'prompt_tokens': X, 'completion_tokens': Y, 'total_tokens': Z}}
    if 'token_usage' in meta:
        u = meta['token_usage']
        return {
            'input_tokens':  u.get('prompt_tokens', 0),
            'output_tokens': u.get('completion_tokens', 0),
            'total_tokens':  u.get('total_tokens', 0),
        }
    # Anthropic: {'usage': {'input_tokens': X, 'output_tokens': Y}}
    if 'usage' in meta:
        u = meta['usage']
        inp = u.get('input_tokens', 0)
        out = u.get('output_tokens', 0)
        return {
            'input_tokens':  inp,
            'output_tokens': out,
            'total_tokens':  inp + out,
        }
    return {}


def get_llm(temperature: float = 0, model_id: str = None):
    mid  = model_id or _active_model
    info = Config.AVAILABLE_MODELS.get(mid, {})
    provider = info.get("provider", "groq")

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=mid,
                temperature=temperature,
                anthropic_api_key=Config.ANTHROPIC_API_KEY,
                max_tokens=2048
            )
        except ImportError:
            raise ImportError(
                "langchain-anthropic tidak terinstall. "
                "Jalankan: pip install langchain-anthropic"
            )

    else:
        return ChatGroq(
            model=mid,
            temperature=temperature,
            groq_api_key=Config.GROQ_API_KEY,
        ) 

_INTENT_KEYWORDS = [
    ("greeting",         ["halo", "hai", "hello", "hi ", "selamat pagi", "selamat siang", "selamat malam", "selamat sore", "assalamu"]),
    ("schema_question",  ["tabel apa saja", "kolom apa", "struktur database", "ada tabel apa", "schema database", "skema", "schema"]),
    ("edukasi_question", ["apa itu nl2sql", "cara kerja agent", "bagaimana sistem ini", "apa itu sql agent"]),
    ("report",           ["buatkan laporan", "buat laporan", "laporan lengkap", "laporan data", "generate report", "bikin laporan", "laporan", "report", "tampilkan laporan", "lihat laporan", "report lengkap"]),
    ("comparison",       ["bandingkan ", "dibandingkan dengan", "perbandingan antara", " vs "]),
    ("data_quality",     ["data aneh", "data kotor", "cek kualitas", "ada yang null", "ada null", "ada duplikat", "outlier", "anomali", "data bermasalah", "missing value"]),
    ("statistic",        ["standar deviasi", "std dev", "statistik deskriptif", "min dan max", "describe data"]),
    ("visualization",    ["grafik", "chart", "plot", "diagram", "visualisasi", "gambarkan", "buat grafik", "tampilkan grafik"]),
    ("insight",          ["insight", "analisis mendalam", "jelaskan data", "apa yang menarik", "kesimpulan dari data", "pola data"]),
]

_NON_SQL_KEYWORD_MAP: dict[str, list[str]] = {
    "greeting":        ["halo", "hai", "hello", "hi ", "selamat pagi", "selamat siang",
                        "selamat malam", "selamat sore", "assalamu"],
    "schema_question": ["tabel apa saja", "kolom apa", "struktur database",
                        "ada tabel apa", "schema database", "skema", "schema"],
    "edukasi_question":["apa itu nl2sql", "cara kerja agent",
                        "bagaimana sistem ini", "apa itu sql agent"],
}

_FEATURE_GROUPS = [
    ["grafik", "chart", "visualisasi", "plot", "diagram"],
    ["jelaskan", "insight", "analisis", "kesimpulan"],
    ["standar deviasi", "statistik deskriptif"],
    ["export", "download", "unduh", "simpan laporan"],
]

_KEYWORD_MAP : dict[str, list[str]] = dict(_INTENT_KEYWORDS)

_TABLE_PKS = {
    "dosen":               "id_dosen",
    "fakultas":            "id_fakultas",
    "jabatan_fungsional":  "id_jabatan",
    "remunerasi":          "id_remunerasi",
}

# --- intent classifier (now uses sentence-transformers via intent_classifier.py) ---
        
def _inject_auto_id(sql: str) -> str:
    if not re.match(r'\s*INSERT', sql, re.IGNORECASE):
        return sql

    m_table = re.match(r'\s*INSERT\s+INTO\s+(\w+)', sql, re.IGNORECASE)
    if not m_table:
        return sql

    table = m_table.group(1).lower()
    pk = _TABLE_PKS.get(table)
    if not pk:
        return sql

    if re.search(rf'\b{re.escape(pk)}\b', sql, re.IGNORECASE):
        return sql

    m_cols = re.search(r'INSERT\s+INTO\s+\w+\s*\(([^)]+)\)', sql, re.IGNORECASE)
    if not m_cols:
        return sql

    m_vals = re.search(r'\bVALUES\s*\(', sql, re.IGNORECASE)
    if not m_vals:
        return sql

    pk_expr = f"(SELECT COALESCE(MAX({pk}), 0) + 1 FROM {table})"

    col_start, col_end = m_cols.start(1), m_cols.end(1)
    sql = sql[:col_start] + pk + ", " + m_cols.group(1).strip() + sql[col_end:]

    m_vals = re.search(r'\bVALUES\s*\(', sql, re.IGNORECASE)
    if m_vals:
        sql = sql[:m_vals.end()] + pk_expr + ", " + sql[m_vals.end():]

    return sql

_FOTO_PATH_RE  = re.compile(r'(/foto/[\w.\-]+)', re.IGNORECASE)
_FOTO_UPDATE_KWS = [
    "update foto", "ganti foto", "ubah foto", "perbarui foto",
    "edit foto", "change foto", "set foto",
]

def _preprocess_foto_update(question: str) -> str:
    path_match = _FOTO_PATH_RE.search(question)
    if not path_match:
        return question

    q_lower = question.lower()
    is_update = any(kw in q_lower for kw in _FOTO_UPDATE_KWS) or (
        ("update" in q_lower or "ganti" in q_lower or "ubah" in q_lower
         or "perbarui" in q_lower or "edit" in q_lower)
        and "foto" in q_lower
    )
    if not is_update:
        return question

    foto_path = path_match.group(1)

    name_part = _FOTO_PATH_RE.sub("", question)
    for kw in sorted(_FOTO_UPDATE_KWS, key=len, reverse=True) + [
        "update", "ganti", "ubah", "perbarui", "edit", "change", "set",
        "foto", "dosen", "dengan", "menjadi", "jadi", "ke",
    ]:
        name_part = re.sub(rf'\b{re.escape(kw)}\b', " ", name_part, flags=re.IGNORECASE)
    name_part = re.sub(r'\s+', ' ', name_part).strip(" .,;:")

    if not name_part:
        return question

    return (
        f"UPDATE kolom foto pada tabel dosen: "
        f"SET foto = '{foto_path}' "
        f"WHERE nama_lengkap LIKE '%{name_part}%'"
    )

# def classify_intent(question: str) -> str:
#     q = question.lower().strip()

#     for intent in _NON_SQL_INTENT_LIST:
#         kws = next(kws for i, kws in _INTENT_KEYWORDS if i == intent)
#         if any(kw in q for kw in kws):
#             return intent
#     if sum(1 for g in _FEATURE_GROUPS if any(kw in q for kw in g)) >= 2:
#         return "report"
#     for intent, kws in _INTENT_KEYWORDS:
#         if intent in _NON_SQL_INTENTS:
#             continue
#         if any(kw in q for kw in kws):
#             return intent
#     return "data_query"

# ── Intent-to-pipeline name mapping ──────────────────────────────────────
_INTENT_PIPELINE_MAP: dict[str, str] = {
    "SELECT":           "data_query",
    "GREETING":         "greeting",
    "SCHEMA_QUESTION":  "schema_question",
    "EDUKASI_QUESTION": "edukasi_question",
    "OUT_OF_SCOPE":     "out_of_scope",
    "CLARIFICATION":    "clarification",
}

# Non-SQL intents that bypass SQL generation
_NON_SQL_INTENTS = {"greeting", "schema_question", "edukasi_question", "out_of_scope", "clarification"}


def classify_intent(question: str) -> str:
    """Classify user intent using semantic cosine similarity."""
    result = intent_classifier.classify(question)
    intent = result["intent"]
    mapped = _INTENT_PIPELINE_MAP.get(intent, "data_query")

    # Sub-category detection for SELECT intents (report, visualization, etc.)
    # These are still keyword-based since the LLM prompt handles them the same way
    if mapped == "data_query":
        q = question.lower().strip()
        if sum(1 for g in _FEATURE_GROUPS if any(kw in q for kw in g)) >= 2:
            return "report"
        for intent_name, kws in _INTENT_KEYWORDS:
            if intent_name in _NON_SQL_INTENTS:
                continue
            if any(kw in q for kw in kws):
                return intent_name

    return mapped


def handle_non_sql(intent: str) -> str:
    if intent == "greeting":
        return "Halo! Saya NL2SQL Agent. Tanyakan apa saja tentang data di database ini!"

    if intent == "schema_question":
        # Use schema_retriever to get ALL tables for schema overview
        schema = schema_retriever.get_relevant_schema("", top_k=4)

        tables = []
        for line in schema.split('\n'):
            if line.strip().startswith('TABEL:'):
                table_name = line.split('TABEL:')[1].strip()
                tables.append(table_name)

        relationships = []
        in_relasi_section = False
        for line in schema.split('\n'):
            if 'RELASI ANTAR TABEL' in line:
                in_relasi_section = True
                continue
            if in_relasi_section and '' in line:
                rel = line.strip()
                if rel and not rel.startswith('─') and not rel.startswith('('):
                    relationships.append(rel)
            elif in_relasi_section and (line.strip().startswith('─') or line.strip().startswith('POLA QUERY')):
                break

        response = f"Database ini memiliki **{len(tables)} tabel**:\n"
        for table in tables:
            response += f"- {table}\n"

        if relationships:
            response += f"\n**Relasi antar tabel**:\n"
            for rel in relationships:
                response += f"- {rel}\n"

        response += "\nTanyakan apa saja tentang data di tabel-tabel ini!"
        return response

    if intent == "edukasi_question":
        return "Buka halaman 'Edukasi' di menu atas untuk penjelasan lengkap cara kerja sistem NL2SQL ini"

    if intent == "out_of_scope":
        return (
            "Maaf, pertanyaan tersebut di luar cakupan database universitas ini. "
            "Saya hanya bisa menjawab pertanyaan seputar data dosen, fakultas, "
            "jabatan fungsional, dan remunerasi. Silakan tanyakan hal terkait data tersebut!"
        )

    if intent == "clarification":
        return (
            "Tentu! Silakan perjelas pertanyaan Anda. Misalnya:\n"
            "- 'Tampilkan semua dosen di Fakultas Teknik'\n"
            "- 'Berapa total gaji pokok dosen?'\n"
            "- 'Siapa dosen dengan jabatan Guru Besar?'"
        )

    return None


def clean_sql_output(raw: str) -> str:
    text = raw.strip()

    # Pattern: ```sql\n...\n``` atau ```\n...\n```
    text = re.sub(r'```(?:sql)?\s*\n?(.*?)\n?```', r'\1', text, flags=re.DOTALL | re.IGNORECASE)

    text = text.replace('`', '').strip()

    sql_start_pattern = re.compile(
        r'(?:^|\n)\s*(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|WITH|EXPLAIN|PRAGMA)\b',
        re.IGNORECASE
    )
    
    match = sql_start_pattern.search(text)
    if match:
        text = text[match.start():].strip()

    last_semi = text.rfind(';')
    if last_semi != -1:
        after_semi = text[last_semi + 1:].strip()
        if after_semi and not after_semi.upper().startswith(('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WITH')):
            text = text[:last_semi + 1].strip()

    text = text.rstrip(';').strip()

    return text


def build_prompt(
    question: str, 
    schema: str = None, 
    history_ctx: str = "",
) -> str:
        return f"""Kamu adalah ahli SQL SQLite. Tugasmu HANYA menghasilkan SQL query yang tepat, tanpa ada penjelasan dan teks lain apa pun!

  ATURAN OUTPUT — WAJIB DIIKUTI TANPA PENGECUALIAN           
  1. Output HANYA 1 SQL QUERY — tidak boleh multiple queries 
  2. DILARANG pakai semicolon (;) untuk pisah query          
  3. Tidak ada penjelasan, tidak ada teks, tidak ada comment 
  4. Tidak ada markdown, tidak ada backtick (```)             
  5. Gunakan tabel & kolom PERSIS sesuai schema di atas       
  6. Untuk multi-tabel: gunakan JOIN hanya jika WAJIB         
  7. JOIN hanya boleh digunakan jika pertanyaan MEMBUTUHKAN   
     kolom dari tabel lain untuk ditampilkan atau difilter    
  8. Untuk UPDATE/DELETE: gunakan subquery jika perlu nama    
  9. SELALU gunakan alias tabel (FROM dosen d, bukan FROM dosen)
 10. JANGAN SELECT * — sebutkan kolom secara eksplisit        
 11. Gunakan explicit JOIN, bukan implicit (FROM a,b WHERE)   


{schema}

ATURAN KRITIS — KAPAN PAKAI JOIN:

DECISION RULE (ikuti ini dengan ketat):
  Apakah pertanyaan MEMBUTUHKAN kolom dari tabel lain?
   YA: Gunakan JOIN sesuai relasi FK
   TIDAK: Query HANYA dari tabel yang relevan, TANPA JOIN

CONTOH BENAR vs SALAH:
  Pertanyaan: "berapa total remunerasi?"
   SALAH: SELECT SUM(r.gaji_pokok) FROM remunerasi r JOIN dosen d ON r.id_dosen = d.id_dosen
   BENAR: SELECT SUM(gaji_pokok) FROM remunerasi r

  Pertanyaan: "berapa total gaji pokok dosen bernama Bella?"
   BENAR: SELECT SUM(r.gaji_pokok) FROM remunerasi r
           JOIN dosen d ON r.id_dosen = d.id_dosen
           WHERE d.nama_lengkap LIKE '%Bella%'

  Alasan: JOIN mengubah hasil menjadi INNER JOIN secara default.
  Data yang tidak memiliki pasangan di tabel lain akan HILANG.
  Gunakan JOIN HANYA jika benar-benar diperlukan.

ATURAN KRITIS — KAPAN PAKAI WHERE vs HAVING:

DECISION RULE (ikuti ini dengan ketat):
  Apakah pertanyaan menyebut "rata-rata ... di bawah/lebih dari X"?
   YA: GUNAKAN HAVING AVG(...) < X  ← BUKAN WHERE
   TIDAK: boleh pakai WHERE untuk filter nilai individual

CONTOH BENAR vs SALAH:
  Pertanyaan: "dosen dengan rata-rata gaji pokok di bawah 5000000"
   SALAH:  WHERE r.gaji_pokok < 5000000 GROUP BY d.id_dosen
   BENAR:  GROUP BY d.id_dosen HAVING AVG(r.gaji_pokok) < 5000000

ATURAN KRITIS — ORDER ASC/DESC + LIMIT (TANPA HAVING):
Jika pertanyaan hanya meminta urutan/ranking TANPA filter ambang:
  JANGAN tambahkan HAVING — cukup GROUP BY + ORDER BY + LIMIT

 SALAH: GROUP BY d.id_dosen HAVING AVG > x ORDER BY avg_gaji ASC LIMIT 3
 BENAR: GROUP BY d.id_dosen ORDER BY avg_gaji ASC LIMIT 3


ATURAN KRITIS — SUBQUERY RATA-RATA KESELURUHAN:
Jika perlu membandingkan dengan rata-rata seluruh data:
  GUNAKAN : (SELECT AVG(gaji_pokok) FROM remunerasi)
  JANGAN  : (SELECT AVG(r.gaji_pokok) FROM remunerasi r JOIN dosen d ON ...)
  ALASAN  : Alias di subquery = CORRELATED ke outer query  hasil salah
  ATURAN  : Subquery untuk rata-rata global = SEDERHANA, tanpa alias, tanpa JOIN


ATURAN KRITIS — PERTANYAAN SEDERHANA:
Jika pertanyaan hanya meminta agregasi/jumlah dari SATU tabel
(contoh: jumlah dosen, total remunerasi, jumlah fakultas, dll):
  GUNAKAN  : SELECT COUNT/SUM/AVG langsung dari tabel tersebut
  JANGAN   : Tambahkan JOIN meski schema tabel relasi ikut dikirim
  ALASAN   : JOIN tidak diperlukan jika data cukup dari satu tabel
             dan JOIN bisa menyebabkan data hilang (INNER JOIN default)

ATURAN KRITIS — PENCARIAN NAMA DOSEN (PARTIAL NAME):
Nama dosen dalam database mengandung gelar (Prof., Dr., S.Pd., M.T, dll).
Jika user menyebut sebagian nama, WAJIB pisahkan setiap kata menjadi kondisi LIKE terpisah:

   SALAH: WHERE d.nama_lengkap = 'Rizal Adompo'
   SALAH: WHERE d.nama_lengkap LIKE '%Rizal Adompo%'  ← gagal jika ada kata sisipan
   BENAR: WHERE d.nama_lengkap LIKE '%Rizal%' AND d.nama_lengkap LIKE '%Adompo%'

  Alasan: nama asli bisa 'Prof. Dr. Abdul Rizal Adompo, S.S.T., M.T' —
  token per kata memastikan match meski ada prefix/gelar di antara kata.

CONTOH:
  User: "tampilkan foto Rizal Adompo"
   BENAR: SELECT d.nama_lengkap, d.foto FROM dosen d
           WHERE d.nama_lengkap LIKE '%Rizal%' AND d.nama_lengkap LIKE '%Adompo%'

  User: "data dosen Bella Mardian"
   BENAR: SELECT d.nama_lengkap, d.nidn FROM dosen d
           WHERE d.nama_lengkap LIKE '%Bella%' AND d.nama_lengkap LIKE '%Mardian%'

  User: "tampilkan foto Budi Jaya Ramadhan"
   BENAR: SELECT d.nama_lengkap, d.foto FROM dosen d
           WHERE d.nama_lengkap LIKE '%Budi%' AND d.nama_lengkap LIKE '%Jaya%' AND d.nama_lengkap LIKE '%Ramadhan%'

ATURAN TAMBAHAN — TAMPILKAN FOTO:
Jika user meminta 'tampilkan foto <nama>', SELALU sertakan kolom nama_lengkap bersama foto:
   BENAR: SELECT d.nama_lengkap, d.foto FROM dosen d WHERE ...
   SALAH: SELECT d.foto FROM dosen d WHERE ...  ← tanpa nama tidak informatif


ATURAN KRITIS — INSERT AUTO-ID (PRIMARY KEY WAJIB DIISI):
Kolom ID pada tabel bawaan BUKAN AUTOINCREMENT — wajib diisi dengan subquery MAX+1.
JANGAN lewatkan kolom ID saat INSERT.

  dosen               id_dosen      = (SELECT COALESCE(MAX(id_dosen), 0) + 1 FROM dosen)
  fakultas            id_fakultas   = (SELECT COALESCE(MAX(id_fakultas), 0) + 1 FROM fakultas)
  jabatan_fungsional  id_jabatan    = (SELECT COALESCE(MAX(id_jabatan), 0) + 1 FROM jabatan_fungsional)
  remunerasi          id_remunerasi = (SELECT COALESCE(MAX(id_remunerasi), 0) + 1 FROM remunerasi)

CONTOH:
  User: "tambahkan dosen Berlian Windasari foto /foto/x.jpg"
   BENAR:
    INSERT INTO dosen (id_dosen, nama_lengkap, foto)
    VALUES ((SELECT COALESCE(MAX(id_dosen), 0) + 1 FROM dosen), 'Berlian Windasari', '/foto/x.jpg')

ATURAN KOLOM TIDAK DIKETAHUI saat INSERT:
  Jika user tidak menyebut nilai untuk kolom tertentu, JANGAN sertakan kolom tersebut
  dalam INSERT (biarkan database menggunakan NULL/default).
  Kecuali: id (PK) WAJIB selalu disertakan dengan MAX+1.


ATURAN KRITIS — KOLOM FK (FOREIGN KEY) SAAT INSERT:
MAX+1 HANYA untuk PK tabel yang sedang di-INSERT. JANGAN gunakan MAX+1 untuk FK!
Kolom FK harus dicari dari tabel relasinya berdasarkan nama yang disebutkan user.

PETA RELASI FK (untuk INSERT):
  fakultas.id_dekan    dosen             : (SELECT id_dosen FROM dosen WHERE ...)
  dosen.id_fakultas    fakultas           : (SELECT id_fakultas FROM fakultas WHERE ...)
  dosen.id_jabatan     jabatan_fungsional : (SELECT id_jabatan FROM jabatan_fungsional WHERE ...)
  remunerasi.id_dosen  dosen             : (SELECT id_dosen FROM dosen WHERE ...)

PENCARIAN FK DENGAN NAMA — gunakan LIKE per token:
  Nama "Thoriq Abdul Aziz" 
    WHERE nama_lengkap LIKE '%Thoriq%' AND nama_lengkap LIKE '%Abdul%' AND nama_lengkap LIKE '%Aziz%'

CONTOH BENAR vs SALAH:
  User: "buat fakultas baru Fakultas Peternakan dekan Thoriq Abdul Aziz"

   BENAR — id_dekan dicari dari tabel dosen berdasarkan nama:
    INSERT INTO fakultas (id_fakultas, nama_fakultas, kode_fakultas, dekan, id_dekan)
    VALUES (
      (SELECT COALESCE(MAX(id_fakultas), 0) + 1 FROM fakultas),
      'Fakultas Peternakan', 'FPT', 'Thoriq Abdul Aziz',
      (SELECT id_dosen FROM dosen
       WHERE nama_lengkap LIKE '%Thoriq%' AND nama_lengkap LIKE '%Abdul%' AND nama_lengkap LIKE '%Aziz%')
    )

   SALAH — MAX+1 untuk FK = membuat ID baru, bukan mencari yang sudah ada:
    id_dekan = (SELECT COALESCE(MAX(id_dosen), 0) + 1 FROM dosen)

  User: "tambah dosen Berlian di Fakultas Teknik jabatan Lektor"

   BENAR — id_fakultas dan id_jabatan dicari dari tabel masing-masing:
    INSERT INTO dosen (id_dosen, nama_lengkap, id_fakultas, id_jabatan)
    VALUES (
      (SELECT COALESCE(MAX(id_dosen), 0) + 1 FROM dosen),
      'Berlian',
      (SELECT id_fakultas FROM fakultas WHERE nama_fakultas LIKE '%Teknik%'),
      (SELECT id_jabatan FROM jabatan_fungsional WHERE nama_jabatan LIKE '%Lektor%')
    )


ATURAN KRITIS — UPDATE KOLOM FOTO:
Jika pertanyaan meminta UPDATE kolom foto (path gambar):
  GUNAKAN  : UPDATE dosen SET foto = '<path>' WHERE nama_lengkap LIKE '%<nama>%'
  JANGAN   : SELECT atau JOIN yang tidak perlu

CONTOH UPDATE FOTO:
  Pertanyaan: "UPDATE kolom foto pada tabel dosen: SET foto = '/foto/budi.jpg' WHERE nama_lengkap LIKE '%Budi Jaya%'"
   BENAR: UPDATE dosen SET foto = '/foto/budi.jpg' WHERE nama_lengkap LIKE '%Budi Jaya%'

  Pertanyaan: "UPDATE kolom foto pada tabel dosen: SET foto = '/foto/IMG_123.jpg' WHERE nama_lengkap LIKE '%Bella Mardian%'"
   BENAR: UPDATE dosen SET foto = '/foto/IMG_123.jpg' WHERE nama_lengkap LIKE '%Bella Mardian%'

  CATATAN: Gunakan LIKE dengan % di kedua sisi nama agar toleran terhadap gelar akademik.


[KATEGORI: KONTEKS LANJUTAN]
{history_ctx if history_ctx else "Tidak ada riwayat percakapan sebelumnya."}

PERTANYAAN
{question}

SQL:"""

def generate_sql(
    question: str,
    chat_history: list = None,
    db_path: str = None,
    schema_cache: dict = None,
) -> dict:
    result = {
        "success": False,
        "sql": "",
        "raw_output": "",
        "intent": "sql_question",
        "source": "llm",
        "non_sql_answer": None,
        "ast_validation": {"valid": True, "operation": ""},
        "few_shot_count": 0,
        "error": None,
        "token_usage": {},
    }

    intent = classify_intent(question)
    result["intent"] = intent

    if intent in _NON_SQL_INTENTS:
        result["success"] = True
        result["source"] = "non-sql"
        result["non_sql_answer"] = handle_non_sql(intent)
        return result

    question = _preprocess_foto_update(question)

    schema = schema_retriever.get_relevant_schema(question, top_k=3)

    history_ctx = ""
    if chat_history:
        for h in chat_history[-6:]:
            if h.get("role") == "user":
                history_ctx += f"User tanya: {h['content']}\n"
            elif h.get("role") == "assistant" and h.get("sql"):
                history_ctx += f"SQL yang dipakai: {h['sql']}\n"

    prompt_text = build_prompt(question, schema, history_ctx)

    try:
        llm = get_llm(temperature=0)
        prompt_tmpl = ChatPromptTemplate.from_messages([("human", "{p}")])
        ai_msg = (prompt_tmpl | llm).invoke({"p": prompt_text})
        raw = ai_msg.content if hasattr(ai_msg, 'content') else str(ai_msg)
        result["raw_output"] = raw
        result["token_usage"] = _extract_token_usage(ai_msg)
    except Exception as e:
        result["error"] = f"LLM error: {str(e)}"
        return result

    sql = clean_sql_output(raw)
    sql = _inject_auto_id(sql)
    result["sql"] = sql

    if not sql:
        result["error"] = "LLM tidak menghasilkan SQL yang valid."
        return result
        
    first_word = sql.strip().upper().split()[0] if sql.strip() else ""
    valid_keywords = {"SELECT", "INSERT", "UPDATE", "DELETE", "DROP",
                      "CREATE", "ALTER", "WITH", "EXPLAIN", "PRAGMA"}
    if first_word not in valid_keywords:
        result["error"] = f"Output bukan SQL valid. Ditemukan: '{first_word}'"
        return result

    result["success"] = True
    result["ast_validation"] = {"valid": True, "operation": first_word}
    return result

def auto_repair_sql(
    question: str,
    broken_sql: str,
    error_message: str,
    schema_cache: dict = None
) -> dict:
    """
    Kirim SQL error ke LLM untuk diperbaiki.
    Dipanggil otomatis saat execute_sql gagal.
    """
    try:
        llm = get_llm(temperature=0)
        schema = schema_retriever.get_relevant_schema(question, top_k=3)

        repair_prompt = f"""Kamu ahli SQL. Perbaiki SQL berikut yang menghasilkan error.

{schema}

PERTANYAAN ASLI: "{question}"

SQL YANG ERROR:
{broken_sql}

PESAN ERROR: {error_message}

Perbaiki SQL di atas. Output HANYA SQL yang sudah diperbaiki, tanpa penjelasan apapun.

SQL DIPERBAIKI:"""

        prompt = ChatPromptTemplate.from_messages([("human", "{p}")])
        chain = prompt | llm | StrOutputParser()
        raw = chain.invoke({"p": repair_prompt})
        repaired = clean_sql_output(raw)
        repaired = _inject_auto_id(repaired)

        if repaired and repaired.strip().upper().split()[0] if repaired.strip() else "" in {
            "SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "WITH"
        }:
            return {"success": True, "sql": repaired}
        return {"success": False, "sql": "", "error": "Repair gagal menghasilkan SQL valid."}

    except Exception as e:
        return {"success": False, "sql": "", "error": str(e)}


def generate_natural_answer(question: str, sql: str, result: dict) -> str:
    try:
        llm = get_llm(temperature=0.1)

        if result.get("columns") and result.get("rows"):
            cols = result["columns"]
            rows = result["rows"][:15]
            data_str = " | ".join(cols) + "\n"
            data_str += "─" * 50 + "\n"
            for row in rows:
                data_str += " | ".join(str(v) if v is not None else "NULL" for v in row) + "\n"
            if result["rowcount"] > 15:
                data_str += f"... dan {result['rowcount'] - 15} baris lainnya"

            msg = (
                f'Pertanyaan: "{question}"\n\n'
                f"Hasil ({result['rowcount']} baris):\n{data_str}\n\n"
                "Tulis jawaban natural dalam Bahasa Indonesia. Sebutkan fakta/angka penting. Maks 3 kalimat. "
                "JANGAN tulis kode SQL, JANGAN gunakan markdown (```, #, **, dll), hanya teks biasa."
            )
        elif result.get("rowcount", 0) > 0:
            msg = (
                f"Operasi database berhasil.\n"
                f"Baris terpengaruh: {result['rowcount']}\n"
                "Konfirmasi singkat dalam Bahasa Indonesia, 1 kalimat, hanya teks biasa tanpa markdown."
            )
        else:
            msg = (
                f'Pertanyaan: "{question}"\n'
                "Hasil: Tidak ada data ditemukan.\n"
                "Sampaikan dengan sopan dalam Bahasa Indonesia + saran pertanyaan ulang. 2 kalimat, hanya teks biasa."
            )

        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "Kamu asisten data yang menjawab dalam Bahasa Indonesia. "
                "WAJIB: hanya teks biasa, DILARANG menulis kode SQL, markdown, atau backtick apapun."
            )),
            ("human", msg)
        ])
        answer = (prompt | llm | StrOutputParser()).invoke({})

        answer = answer.replace("```sql", "").replace("```", "").strip()
        return answer

    except Exception:
        if result.get("rows"):
            return f"Ditemukan {result['rowcount']} data sesuai permintaan Anda."
        if result.get("rowcount", 0) > 0:
            return f"Operasi berhasil. {result['rowcount']} baris terpengaruh."
        return "Tidak ada data yang sesuai dengan pertanyaan tersebut."



def explain_sql_error_friendly(question: str, sql: str, error: str) -> str:
    try:
        llm = get_llm(temperature=0.1)
        prompt = ChatPromptTemplate.from_messages([
            ("system", "Jelaskan error database dengan bahasa sederhana untuk siswa."),
            ("human", (
                f'Pertanyaan: "{question}"\nSQL: {sql}\nError: {error}\n\n'
                "Jelaskan: apa yang salah dan saran perbaikan. Maks 2 kalimat sederhana."
            ))
        ])
        return (prompt | llm | StrOutputParser()).invoke({})
    except Exception:
        return "Terjadi kesalahan. Coba rumuskan pertanyaan lebih spesifik."


def generate_insight(question: str, columns: list, rows: list) -> str:
    try:
        import pandas as pd
        df = pd.DataFrame(rows[:100], columns=columns)

        lines = [
            f"Jumlah baris: {len(rows)}",
            f"Kolom: {', '.join(columns)}",
            f"\nContoh data (10 baris):\n{df.head(10).to_string(index=False)}",
        ]
        num_cols = df.select_dtypes(include="number").columns.tolist()
        if num_cols:
            lines.append(f"\nStatistik numerik:\n{df[num_cols].describe().round(2).to_string()}")

        llm = get_llm(temperature=0.3)
        prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "Kamu analis data universitas. Berikan 3-4 insight penting dari data ini dalam Bahasa Indonesia. "
                "Fokus: tren, pola menarik, nilai ekstrem, anomali. "
                "Format: kalimat pendek, hanya teks biasa tanpa markdown atau simbol."
            )),
            ("human", f'Pertanyaan user: "{question}"\n\nData:\n' + "\n".join(lines)),
        ])
        result = (prompt | llm | StrOutputParser()).invoke({})
        return result.replace("```", "").strip()
    except Exception as e:
        return f"Insight tidak tersedia: {str(e)}"

def calculate_statistics(columns: list, rows: list, question: str = "") -> dict:
    try:
        import pandas as pd
        df = pd.DataFrame(rows, columns=columns)
        num_cols = df.select_dtypes(include="number").columns.tolist()

        if not num_cols:
            return {"success": False, "message": "Tidak ada kolom numerik.", "stats": {}}

        q = question.lower()
        stats = {}
        for col in num_cols:
            series = df[col].dropna()
            if len(series) == 0:
                continue
            want_all = not any(kw in q for kw in [
                "rata-rata", "mean", "median", "standar deviasi", "std",
                "minimum", "min ", "maximum", "max "
            ])
            entry = {}
            if want_all or any(kw in q for kw in ["rata-rata", "mean", "average"]):
                entry["rata_rata"] = round(float(series.mean()), 2)
            if want_all or "median" in q:
                entry["median"] = round(float(series.median()), 2)
            if want_all or any(kw in q for kw in ["standar deviasi", "std", "deviasi"]):
                entry["std_deviasi"] = round(float(series.std()), 2)
            if want_all or any(kw in q for kw in ["minimum", "min ", "terkecil"]):
                entry["minimum"] = round(float(series.min()), 2)
            if want_all or any(kw in q for kw in ["maximum", "max ", "terbesar"]):
                entry["maksimum"] = round(float(series.max()), 2)
            if want_all:
                entry["jumlah_data"] = int(series.count())
            stats[col] = entry

        return {"success": True, "stats": stats, "columns": num_cols}
    except Exception as e:
        return {"success": False, "message": str(e), "stats": {}}

def check_data_quality(columns: list, rows: list) -> dict:
    try:
        import pandas as pd
        df = pd.DataFrame(rows, columns=columns)
        issues = []

        for col in columns:
            cnt = int(df[col].isnull().sum())
            if cnt > 0:
                pct = round(cnt / len(df) * 100, 1)
                issues.append({
                    "type": "null", "column": col, "count": cnt, "pct": pct,
                    "message": f"'{col}': {cnt} nilai kosong ({pct}%)"
                })

        dup = int(df.duplicated().sum())
        if dup > 0:
            issues.append({
                "type": "duplicate", "count": dup,
                "message": f"{dup} baris duplikat ditemukan"
            })

        num_cols = df.select_dtypes(include="number").columns.tolist()
        for col in num_cols:
            series = df[col].dropna()
            if len(series) < 4:
                continue
            Q1, Q3 = series.quantile(0.25), series.quantile(0.75)
            IQR = Q3 - Q1
            lower, upper = Q1 - 1.5 * IQR, Q3 + 1.5 * IQR
            outliers = series[(series < lower) | (series > upper)]
            if len(outliers) > 0:
                issues.append({
                    "type": "outlier", "column": col,
                    "count": int(len(outliers)),
                    "lower": round(float(lower), 2),
                    "upper": round(float(upper), 2),
                    "sample_values": [round(float(v), 2) for v in outliers.tolist()[:5]],
                    "message": f"'{col}': {len(outliers)} outlier di luar [{round(float(lower), 2)}, {round(float(upper), 2)}]"
                })

        null_issues = [i for i in issues if issues['type'] == 'null']
        print(null_issues)
        score = max(0, 100 - len(issues) * 15)
        grade = "Baik" if score >= 80 else "Cukup" if score >= 50 else "Perlu Perbaikan"

        return {
            "success": True,
            "issues": issues,
            "summary": {
                "total_rows": len(df),
                "total_cols": len(columns),
                "issue_count": len(issues),
                "quality_score": score,
                "grade": grade,
            }
        }
    except Exception as e:
        return {"success": False, "issues": [], "message": str(e)}
