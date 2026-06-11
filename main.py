import os
import io
import re
from typing import Optional, List

from pydantic import BaseModel, Field

import uvicorn
from fastapi import (
    FastAPI, Request, Depends, HTTPException, status,
    Form, UploadFile, File,
)
from fastapi.responses import (
    HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse, FileResponse
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm

from config import Config
from auth import (
    setup_user_database, verify_credentials, create_access_token,
    get_current_user, require_admin, get_user_from_cookie,
    get_all_users, add_user,
)
from agent import (
    generate_sql, auto_repair_sql,
    generate_natural_answer, explain_sql_error_friendly,
    generate_insight, calculate_statistics, check_data_quality,
    set_active_model, get_active_model, get_active_model_info,
)
from guards import (
    check_sql_permission, validate_sql_syntax,
    set_demo_mode, is_demo_mode,
)
from utils import (
    load_schema_to_cache, get_schema_for_display,
    execute_sql, run_explain_query,
    log_to_audit, get_audit_logs,
    export_to_csv, export_to_excel,
    process_uploaded_db, process_uploaded_csv,
    save_chat_message, get_chat_history, clear_chat_history,
)
from query_cache import (
    get_cached_result, set_cached_result, invalidate_cache, get_cache_stats,
)
from observability import record_request, get_metrics, Timer
from query_optimizer import (
    evaluate_sql, save_optimization_result, get_optimization_stats,
    get_optimization_history, setup_optimization_table,
)
from visualizer import detect_viz_intent, generate_chart
from database_setup import init_all

app = FastAPI(title="NL2SQL Agent", version="3.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
os.makedirs("foto", exist_ok=True)
app.mount("/foto", StaticFiles(directory="foto"), name="foto")
templates = Jinja2Templates(directory="templates")

_active_db: dict[str, str] = {}


def _get_db(username: str = "") -> str:
    return _active_db.get(username, Config.DATABASE_PATH)


@app.on_event("startup")
async def startup():
    init_all()
    setup_user_database()
    load_schema_to_cache()
    setup_optimization_table()
    print("[APP] NL2SQL FastAPI siap.")

class ChatMessage(BaseModel):
    """Chat history message"""
    role: str = Field(..., description="Role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    sql: Optional[str] = Field(None, description="SQL query (for assistant messages)")

class AskRequest(BaseModel):
    """Request body untuk /api/ask"""
    question: str = Field(..., description="Pertanyaan dalam bahasa natural", example="Tampilkan semua mahasiswa")
    force_execute: bool = Field(False, description="Force execute tanpa konfirmasi (untuk admin)")
    pre_sql: Optional[str] = Field(None, description="Pre-generated SQL untuk konfirmasi")
    chat_history: List[ChatMessage] = Field(default_factory=list, description="Riwayat chat untuk context")

# AUTH PAGE

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    user = await get_user_from_cookie(request)
    if user:
        return RedirectResponse("/chat")
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login_form(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Login via HTML form — set token di cookie httponly."""
    user = verify_credentials(username, password)
    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request,
             "error": "Username atau password salah."},
            status_code=400,
        )
    token    = create_access_token(user["username"], user["role"], user["name"])
    response = RedirectResponse("/chat", status_code=302)
    response.set_cookie(
        "access_token", token,
        httponly=True,
        max_age=8 * 3600,
        samesite="lax",
    )
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("access_token")
    return response


# CHAT PAGE

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse("/")
    
    history = get_chat_history(user["username"], limit=20)
    
    return templates.TemplateResponse("chat.html", {
        "request":        request,
        "user":           user,
        "schema":         get_schema_for_display(),
        "chat_history":   history,
        "demo_mode":      is_demo_mode(),
        "active_model":   get_active_model(),
        "active_model_info": get_active_model_info(),
        "available_models": Config.AVAILABLE_MODELS,
    })


# ADMIN PAGE (belum ada)

@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse("/")
    if user.get("role") != "admin":
        return RedirectResponse("/chat")
    return templates.TemplateResponse("admin_dashboard.html", {
        "request":      request,
        "user":         user,
        "logs":         get_audit_logs(200),
        "metrics":      get_metrics(),
        "cache_stats":  get_cache_stats(),
        "all_users":    get_all_users(),
        "demo_mode":    is_demo_mode(),
        "opt_stats":    get_optimization_stats(),
        "opt_history":  get_optimization_history(10),
    })


# PANDUAN PAGE

@app.get("/panduan", response_class=HTMLResponse)
async def edukasi_page(request: Request):
    user = await get_user_from_cookie(request)
    if not user:
        return RedirectResponse("/")
    return templates.TemplateResponse("panduan.html", {
        "request": request,
        "user":    user,
    })


@app.post("/api/ask")
async def api_ask(
    body: AskRequest,
    user:    dict = Depends(get_current_user),
):
    question      = body.question.strip()
    force_execute = body.force_execute
    pre_sql       = body.pre_sql
    chat_history_from_client = [msg.dict() for msg in body.chat_history]
    
    if chat_history_from_client:
        chat_history = chat_history_from_client
    else:
        chat_history_raw = get_chat_history(user["username"], limit=20)
        chat_history = [
            {"role": h["role"], "content": h["content"], "sql": h.get("sql_query")}
            for h in chat_history_raw
        ]

    if not question and not pre_sql:
        raise HTTPException(status_code=400, detail="Pertanyaan tidak boleh kosong.")

    username  = user["username"]
    role      = user["role"]
    active_db = _get_db(username)

    payload = {
        "question":      question or "Konfirmasi eksekusi",
        "sql":           "",
        "raw_output":    "",
        "explain":       None,
        "table":         None,
        "answer":        "",
        "guard":         None,
        "needs_confirm": False,
        "error":         None,
        "meta": {
            "intent":        "sql_question",
            "source":        "llm",
            "cache_hit":     False,
            "auto_repaired": False,
            "demo_mode":     is_demo_mode(),
            "model_id":      get_active_model(),
            "model_label":   get_active_model_info().get("label", get_active_model()),
            "provider":      get_active_model_info().get("provider", "groq"),
        },
    }

    if pre_sql:
        payload["sql"] = pre_sql
        return _run_pipeline(
            pre_sql, question or "Konfirmasi", username, role,
            active_db, payload, force_execute=True,
        )

    with Timer() as t_gen:
        gen = generate_sql(question=question, chat_history=chat_history)
    sql_gen_ms = t_gen.elapsed_ms

    payload["meta"]["intent"]      = gen.get("intent", "sql_question")
    payload["meta"]["source"]      = gen.get("source", "llm")
    payload["meta"]["token_usage"] = gen.get("token_usage", {})

    if gen.get("source") == "non-sql":
        payload["answer"] = gen.get("non_sql_answer", "")
        record_request(sql_gen_ms=sql_gen_ms, success=True)

        save_chat_message(username, "user", question)
        save_chat_message(username, "assistant", payload["answer"])
        return JSONResponse(payload)

    if not gen["success"]:
        err = gen.get("error") or "LLM error"
        payload["error"]  = err
        payload["answer"] = explain_sql_error_friendly(question, "", err)
        log_to_audit(username, role, question, "", "error", err)
        record_request(sql_gen_ms=sql_gen_ms, success=False)
        return JSONResponse(payload)

    sql = gen["sql"]
    payload["sql"] = sql
    payload["raw_output"] = gen.get("raw_output", "")

    return _run_pipeline(
        sql, question, username, role, active_db, payload,
        sql_gen_ms=sql_gen_ms, force_execute=force_execute,
        intent=gen.get("intent", "data_query"),
    )


def _sanitize_for_json(obj):
    import math
    
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_for_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    else:
        return obj


def _run_pipeline(
    sql: str, question: str, username: str, role: str,
    active_db: str, payload: dict,
    sql_gen_ms: float = 0, force_execute: bool = False,
    intent: str = "data_query",
) -> JSONResponse:
    """Validate → guard → cache → explain → execute → answer."""

    val = validate_sql_syntax(sql)
    if not val["valid"]:
        err = val["error"] or "SQL tidak valid"
        payload["error"]  = err
        payload["answer"] = explain_sql_error_friendly(question, sql, err)
        log_to_audit(username, role, question, sql, "error", err)
        record_request(sql_gen_ms=sql_gen_ms, success=False)
        return JSONResponse(payload)

    guard = check_sql_permission(sql, role)
    payload["guard"] = guard

    if not guard["allowed"]:
        log_to_audit(username, role, question, sql, "blocked", guard["message"])
        payload["answer"] = guard["message"]
        payload["error"]  = guard["message"]
        record_request(blocked=True)
        return JSONResponse(payload)

    if guard["needs_confirm"] and not force_execute:
        payload["explain"]       = run_explain_query(sql, active_db)
        payload["needs_confirm"] = True
        payload["answer"]        = (
            "Query ini dapat mengubah/menghapus data. "
            "Tinjau SQL dan EXPLAIN, lalu konfirmasi eksekusi."
        )
        payload["error"] = None
        log_to_audit(username, role, question, sql, "allowed", "Menunggu konfirmasi")
        return JSONResponse(payload)

    if sql.strip().upper().startswith("SELECT"):
        cached = get_cached_result(sql)
        if cached:
            payload["meta"]["cache_hit"] = True
            payload["table"] = {
                "columns":  cached["columns"],
                "rows":     cached["rows"][:100],
                "rowcount": cached["rowcount"],
                "truncated": cached["rowcount"] > 100,
            }
            payload["answer"] = generate_natural_answer(question, sql, cached)
            log_to_audit(username, role, question, sql, "executed",
                         f"(cache) {cached['rowcount']} baris")
            record_request(sql_gen_ms=sql_gen_ms, cache_hit=True, success=True)
            # Save to chat history with table data
            save_chat_message(username, "user", question)
            save_chat_message(
                username, 
                "assistant", 
                payload["answer"], 
                sql_query=sql,
                table_data=payload.get("table")
            )
            return JSONResponse(payload)

    payload["explain"] = run_explain_query(sql, active_db)

    with Timer() as t_exec:
        result = execute_sql(sql, active_db)
    exec_ms = t_exec.elapsed_ms

    if not result["success"]:
        # Auto-repair
        repair = auto_repair_sql(question, sql, result["error"])
        if repair["success"]:
            result2 = execute_sql(repair["sql"], active_db)
            if result2["success"]:
                sql                          = repair["sql"]
                payload["sql"]               = sql
                payload["meta"]["auto_repaired"] = True
                result                       = result2
            else:
                return _error_response(
                    payload, question, sql, result["error"],
                    username, role, sql_gen_ms, exec_ms,
                )
        else:
            return _error_response(
                payload, question, sql, result["error"],
                username, role, sql_gen_ms, exec_ms,
            )

    payload["table"] = {
        "columns":  result["columns"],
        "rows":     result["rows"][:100],
        "rowcount": result["rowcount"],
        "truncated": result["rowcount"] > 100,
    }
    payload["answer"] = generate_natural_answer(question, sql, result)

    name_warning = _check_name_mismatch(question, sql)
    if name_warning:
        payload["name_warning"] = name_warning
        if result["rowcount"] > 0:
            payload["answer"] = name_warning["message"]
            payload["table"]  = None
            payload["meta"]["name_mismatch"] = True
            log_to_audit(username, role, question, sql, "blocked",
                         f"Name mismatch: user='{name_warning['user_name']}' sql='{name_warning['sql_name']}'")
            record_request(sql_gen_ms=sql_gen_ms, exec_ms=exec_ms,
                           success=False, blocked=True)
            return JSONResponse(payload)

    if result["rowcount"] == 0 and sql.strip().upper().startswith("SELECT"):
        suggestions = _detect_and_suggest_partial_name(question, sql, active_db)
        if suggestions:
            payload["meta"]["partial_name_suggestions"] = suggestions
            names_str = ", ".join(f"'{n}'" for n in suggestions)
            payload["answer"] = (
                f"Nama yang Anda cari tidak ditemukan secara persis. "
                f"Apakah yang Anda maksud: {names_str}? "
                f"Silakan coba dengan nama lengkap."
            )

    opt_result = evaluate_sql(sql, question, payload.get("explain"))
    payload["optimization"] = {
        "score":        opt_result["score"],
        "grade":        opt_result["grade"],
        "summary":      opt_result["summary"],
        "findings":     opt_result["findings"],
        "categories":   opt_result["categories"],
        "explain_info": opt_result["explain_info"],
        "optimized_sql": opt_result.get("optimized_sql"),
    }
    save_optimization_result(username, question, sql, opt_result)

    _need_viz = (
        detect_viz_intent(question)
        or intent in ("visualization", "comparison", "report")
    )
    if _need_viz and result.get("rows") and result.get("columns"):
        viz = generate_chart(
            columns  = result["columns"],
            rows     = result["rows"],
            question = question,
        )
        if viz["success"]:
            payload["visualization"] = {
                "chart_type": viz["chart_type"],
                "chart_b64":  viz["chart_b64"],
                "reason":     viz.get("reason", ""),
            }
        else:
            payload["visualization"] = {
                "error": viz.get("error", "Gagal menghasilkan grafik.")
            }

    if intent in ("insight", "report", "comparison") and result.get("rows") and result.get("columns"):
        payload["insight"] = generate_insight(question, result["columns"], result["rows"])

    if intent in ("statistic", "report") and result.get("rows") and result.get("columns"):
        stats = calculate_statistics(result["columns"], result["rows"], question)
        if stats.get("success") and stats.get("stats"):
            payload["statistics"] = stats["stats"]

    if intent == "comparison" and result.get("rows") and result.get("columns"):
        if payload.get("insight"):
            payload["answer"] = payload["insight"]

    if intent == "data_quality" and result.get("rows") and result.get("columns"):
        quality = check_data_quality(result["columns"], result["rows"])
        payload["data_quality"] = quality
        if quality.get("success") and quality.get("summary"):
            s = quality["summary"]
            payload["answer"] = (
                f"Hasil pemeriksaan kualitas data: {s['total_rows']} baris, "
                f"{s['issue_count']} masalah ditemukan. "
                f"Skor kualitas: {s['quality_score']}/100 ({s['grade']})."
            )

    if intent == "report":
        if not payload.get("insight") and result.get("rows") and result.get("columns"):
            payload["insight"] = generate_insight(question, result["columns"], result["rows"])
        if not payload.get("statistics") and result.get("rows") and result.get("columns"):
            stats = calculate_statistics(result["columns"], result["rows"])
            if stats.get("success") and stats.get("stats"):
                payload["statistics"] = stats["stats"]
        quality = check_data_quality(result["columns"], result["rows"]) if result.get("rows") else {}
        if quality.get("success"):
            payload["data_quality"] = quality
        payload["is_report"] = True

    if sql.strip().upper().startswith("SELECT"):
        set_cached_result(sql, result)
    else:
        invalidate_cache()

    log_to_audit(username, role, question, sql, "executed", f"{result['rowcount']} baris")
    record_request(
        sql_gen_ms=sql_gen_ms, exec_ms=exec_ms, success=True,
        auto_repaired=payload["meta"].get("auto_repaired", False),
    )

    payload = _sanitize_for_json(payload)

    save_chat_message(username, "user", question)
    save_chat_message(
        username, 
        "assistant", 
        payload["answer"], 
        sql_query=sql,
        table_data=payload.get("table"),
        visualization=payload.get("visualization"),
        metadata={
            "insight": payload.get("insight"),
            "statistics": payload.get("statistics"),
            "data_quality": payload.get("data_quality"),
            "optimization": payload.get("optimization"),
            "is_report": payload.get("is_report", False)
        }
    )

    return JSONResponse(payload)


def _error_response(payload, question, sql, error, username, role, sql_gen_ms, exec_ms):
    err               = explain_sql_error_friendly(question, sql, error)
    payload["error"]  = err
    payload["answer"] = err
    log_to_audit(username, role, question, sql, "error", error)
    record_request(sql_gen_ms=sql_gen_ms, exec_ms=exec_ms, success=False)
    return JSONResponse(payload)


PERSON_NAME_FIELDS = [
    {"table": "dosen", "columns": ["nama_lengkap"]},
    {"table": "fakultas", "columns": ["nama_fakultas"]},
    {"table": "jabatan_fungsional", "columns": ["nama_jabatan"]},
]


def _build_name_regex() -> re.Pattern:
    columns = {col for f in PERSON_NAME_FIELDS for col in f["columns"]}
    col_pattern = "|".join(re.escape(c) for c in columns)
    return re.compile(
        rf"WHERE\s+(?:\w+\.)?(?:{col_pattern})\s*=\s*'([^']+)'",
        re.IGNORECASE
    )


_NAME_REGEX = _build_name_regex()


def _fetch_all_names(db_path: str) -> list[dict]:
    import sqlite3
    results = []
    try:
        conn = sqlite3.connect(db_path)
        for field in PERSON_NAME_FIELDS:
            table   = field["table"]
            columns = field["columns"]
            try:
                if len(columns) == 1:
                    col = columns[0]
                    rows = conn.execute(
                        f"SELECT {col} FROM {table} WHERE {col} IS NOT NULL"
                    ).fetchall()
                    for (name,) in rows:
                        results.append({"name": name, "table": table})
                else:
                    concat_expr = " || ' ' || ".join(
                        f"COALESCE({c}, '')" for c in columns
                    )
                    rows = conn.execute(
                        f"SELECT TRIM({concat_expr}) FROM {table}"
                    ).fetchall()
                    for (name,) in rows:
                        if name.strip():
                            results.append({"name": name, "table": table})
            except Exception:
                continue
        conn.close()
    except Exception:
        pass
    return results


def _check_name_mismatch(question: str, sql: str) -> dict | None:
    import difflib

    if not sql.strip().upper().startswith("SELECT"):
        return None

    name_patterns = [
        r'(?:nilai|tampilkan|cari|lihat|data|untuk|dari|tamu|staff|bernama)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
    ]
    stop_words = {
        'Tampilkan', 'Nilai', 'Data', 'Semua', 'Kelas', 'Mata',
        'Pelajaran', 'Tamu', 'Staff', 'Kamar', 'Booking', 'Layanan',
    }

    user_name = None
    for pattern in name_patterns:
        match = re.search(pattern, question)
        if match:
            candidate = match.group(1).strip()
            if candidate not in stop_words and len(candidate) >= 4:
                user_name = candidate
                break

    if not user_name:
        return None

    sql_name_match = _NAME_REGEX.search(sql)
    if not sql_name_match:
        return None

    sql_name = sql_name_match.group(1)

    if user_name.lower() == sql_name.lower():
        return None

    sim = difflib.SequenceMatcher(None, user_name.lower(), sql_name.lower()).ratio()

    if sim > 0.70:
        return {
            "user_name":  user_name,
            "sql_name":   sql_name,
            "similarity": round(sim, 2),
            "message": (
                f"⚠️ Nama '{user_name}' tidak ditemukan di database. "
                f"Sistem mendeteksi nama yang Anda maksud mungkin berbeda dari '{sql_name}'. "
                f"Mohon periksa ejaan nama dan coba lagi dengan nama yang tepat."
            ),
        }

    return None


def _suggest_similar_names(partial_name: str, db_path: str) -> list[str]:
    import difflib

    all_entries = _fetch_all_names(db_path)
    partial_lower = partial_name.lower()
    seen    = set()
    matches = []

    for entry in all_entries:
        name = entry["name"]
        if name in seen:
            continue
        name_words = name.lower().split()
        is_match = (
            any(partial_lower in word or word in partial_lower for word in name_words)
            or difflib.SequenceMatcher(None, partial_lower, name.lower()).ratio() > 0.6
        )
        if is_match:
            seen.add(name)
            matches.append(name)

    return matches[:5]


def _detect_and_suggest_partial_name(question: str, sql: str, db_path: str) -> list[str]:
    import difflib

    sql_name_match = _NAME_REGEX.search(sql)
    if not sql_name_match:
        return []

    searched_name = sql_name_match.group(1).strip()

    if len(searched_name.split()) == 1:
        return _suggest_similar_names(searched_name, db_path)

    all_entries = _fetch_all_names(db_path)
    seen  = set()
    close = []

    for entry in all_entries:
        name = entry["name"]
        if name in seen or name.lower() == searched_name.lower():
            continue
        if difflib.SequenceMatcher(None, searched_name.lower(), name.lower()).ratio() > 0.75:
            seen.add(name)
            close.append(name)

    return close[:3]


@app.post("/api/clear-history")
async def api_clear_history(user: dict = Depends(get_current_user)):
    """Clear chat history from database."""
    clear_chat_history(user["username"])
    return {"success": True, "message": "Chat history cleared"}


@app.get("/api/chat-history")
async def api_get_chat_history(user: dict = Depends(get_current_user)):
    """Get chat history for current user."""
    history = get_chat_history(user["username"], limit=20)
    return {"success": True, "history": history}



@app.get("/api/models")
async def api_list_models(user: dict = Depends(get_current_user)):
    """Daftar semua model yang tersedia."""
    active = get_active_model()
    models = []
    for mid, info in Config.AVAILABLE_MODELS.items():
        available = True
        if info["provider"] == "anthropic" and not Config.ANTHROPIC_API_KEY:
            available = False
        if info["provider"] == "groq" and not Config.GROQ_API_KEY:
            available = False
        models.append({
            "id":       mid,
            "active":   mid == active,
            "available": available,
            **info,
        })
    return {"models": models, "active": active}


@app.post("/api/model/switch")
async def api_switch_model(
    request: Request,
    user: dict = Depends(get_current_user),
):
    """Ganti model aktif."""
    data     = await request.json()
    model_id = data.get("model_id", "")

    if model_id not in Config.AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail=f"Model '{model_id}' tidak tersedia.")

    info = Config.AVAILABLE_MODELS[model_id]

    # Cek API key tersedia
    if info["provider"] == "anthropic" and not Config.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="ANTHROPIC_API_KEY belum dikonfigurasi di .env"
        )
    if info["provider"] == "groq" and not Config.GROQ_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="GROQ_API_KEY belum dikonfigurasi di .env"
        )

    success = set_active_model(model_id)
    if not success:
        raise HTTPException(status_code=400, detail="Gagal mengganti model.")

    return {
        "success":    True,
        "model_id":   model_id,
        "model_info": info,
        "message":    f"Model diganti ke {info['label']}",
    }


@app.get("/api/schema")
async def api_schema(user: dict = Depends(get_current_user)):
    return get_schema_for_display()


@app.post("/api/reload-schema")
async def api_reload_schema(user: dict = Depends(get_current_user)):
    db = _get_db(user["username"])
    load_schema_to_cache(db)
    invalidate_cache()
    return {"success": True, "message": "Schema & cache di-reload."}


@app.post("/api/demo-mode")
async def api_demo_mode(
    request: Request,
    user:    dict = Depends(require_admin),
):
    data    = await request.json()
    enabled = data.get("enabled", False)
    set_demo_mode(enabled)
    return {
        "success":   True,
        "demo_mode": is_demo_mode(),
        "message":   f"Demo Mode {'AKTIF 🔒' if enabled else 'dinonaktifkan'}",
    }


@app.get("/api/demo-mode/status")
async def api_demo_status(user: dict = Depends(get_current_user)):
    return {"demo_mode": is_demo_mode()}


@app.post("/api/export/csv")
async def api_export_csv(
    request: Request,
    user:    dict = Depends(get_current_user),
):
    data    = await request.json()
    content = export_to_csv(data.get("columns", []), data.get("rows", []))
    return StreamingResponse(
        io.StringIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=hasil_query.csv"},
    )


@app.post("/api/export/excel")
async def api_export_excel(
    request: Request,
    user:    dict = Depends(get_current_user),
):
    data  = await request.json()
    excel = export_to_excel(data.get("columns", []), data.get("rows", []))
    if excel is None:
        raise HTTPException(status_code=500, detail="openpyxl tidak terinstall.")
    return StreamingResponse(
        io.BytesIO(excel),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=hasil_query.xlsx"},
    )


@app.post("/api/export/report")
async def api_export_report(
    request: Request,
    user:    dict = Depends(get_current_user),
):
    data     = await request.json()
    question = data.get("question", "")
    columns  = data.get("columns", [])
    rows     = data.get("rows", [])
    answer   = data.get("answer", "")
    insight  = data.get("insight", "")
    sql      = data.get("sql", "")
    stats    = data.get("statistics", {})

    thead = "".join(f"<th>{c}</th>" for c in columns)
    tbody = "".join(
        "<tr>" + "".join(f"<td>{cell if cell is not None else ''}</td>" for cell in row) + "</tr>"
        for row in rows[:500]
    )

    stats_html = ""
    if stats:
        stats_rows = ""
        for col, s in stats.items():
            stats_rows += f"<tr><td><b>{col}</b></td>" + "".join(
                f"<td>{v}</td>" for v in s.values()
            ) + "</tr>"
        stat_headers = list(next(iter(stats.values())).keys()) if stats else []
        stats_html = f"""
        <h2>Statistik Deskriptif</h2>
        <table><thead><tr><th>Kolom</th>{"".join(f"<th>{h}</th>" for h in stat_headers)}</tr></thead>
        <tbody>{stats_rows}</tbody></table>"""

    html = f"""<!DOCTYPE html>
<html lang="id"><head><meta charset="utf-8">
<title>Laporan NL2SQL — {question}</title>
<style>
  body {{ font-family: Arial, sans-serif; padding: 24px; color: #1e293b; }}
  h1   {{ font-size: 20px; border-bottom: 2px solid #2563eb; padding-bottom: 8px; }}
  h2   {{ font-size: 15px; color: #2563eb; margin-top: 20px; }}
  p    {{ font-size: 13px; line-height: 1.6; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 8px; font-size: 12px; }}
  th   {{ background: #2563eb; color: #fff; padding: 6px 10px; text-align: left; }}
  td   {{ border: 1px solid #e2e8f0; padding: 5px 10px; }}
  tr:nth-child(even) td {{ background: #f8fafc; }}
  pre  {{ background: #f1f5f9; padding: 12px; border-radius: 6px; font-size: 11px; overflow-x: auto; }}
  .meta {{ font-size: 11px; color: #64748b; margin-bottom: 16px; }}
  @media print {{ button {{ display: none; }} }}
</style>
</head><body>
<h1>Laporan Data</h1>
<p class="meta">Digenerate oleh NL2SQL Agent &nbsp;|&nbsp; {user["name"]} ({user["role"]})</p>

<h2>Pertanyaan</h2>
<p>{question}</p>

<h2>Ringkasan Jawaban</h2>
<p>{answer}</p>

{"<h2>Insight AI</h2><p>" + insight + "</p>" if insight else ""}

<h2>Data ({len(rows)} baris)</h2>
<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>
{"..." if len(rows) > 500 else ""}

{stats_html}

{"<h2>SQL Query</h2><pre>" + sql + "</pre>" if sql else ""}

<br><button onclick="window.print()" style="padding:8px 16px;background:#2563eb;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px">
  Cetak / Simpan PDF
</button>
</body></html>"""

    return HTMLResponse(content=html)


ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


@app.post("/api/upload/foto")
async def api_upload_foto(
    user: dict = Depends(get_current_user),
    file: UploadFile = File(...),
):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Format '.{ext}' tidak didukung. Gunakan: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}",
        )

    # Sanitize filename: hanya huruf, angka, strip, titik
    import re
    safe_name = re.sub(r"[^\w\.\-]", "_", file.filename)
    save_path = os.path.join("foto", safe_name)

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ukuran foto maks 5 MB.")

    with open(save_path, "wb") as f:
        f.write(content)

    foto_path = f"/foto/{safe_name}"
    return {
        "success": True,
        "filename": safe_name,
        "path": foto_path,
        "message": f"Foto berhasil diupload. Path: {foto_path}",
    }



@app.get("/api/audit-logs")
async def api_audit_logs(user: dict = Depends(require_admin)):
    return get_audit_logs(200)


@app.get("/api/metrics")
async def api_metrics(user: dict = Depends(require_admin)):
    return get_metrics()


@app.get("/api/optimization/stats")
async def api_opt_stats(user: dict = Depends(require_admin)):
    """Statistik optimasi untuk admin dashboard."""
    return get_optimization_stats()


@app.get("/api/optimization/history")
async def api_opt_history(user: dict = Depends(require_admin)):
    """Riwayat 20 evaluasi optimasi terbaru."""
    return get_optimization_history(20)


@app.post("/api/add-user")
async def api_add_user(
    request: Request,
    user:    dict = Depends(require_admin),
):
    data   = await request.json()
    result = add_user(
        data.get("username", ""),
        data.get("password", ""),
        data.get("name", ""),
        data.get("role", "user"),
    )
    return result

@app.get('/favicon.ico', include_in_schema=False)
async def favicon():
    return FileResponse('static/favicon.ico')

if __name__ == "__main__":
    print("=" * 55)
    print("  🚀 NL2SQL Agent v3 — FastAPI")
    print("=" * 55)
    print(f"  📁 Database : {Config.DATABASE_PATH}")
    print(f"  🤖 Model    : {Config.GROQ_MODEL}")
    print(f"  🌐 URL      : http://localhost:8000")
    print(f"  📖 API Docs : http://localhost:8000/docs")
    print("=" * 55)
    print("  admin / admin123  →  Full access")
    print("  user  / user123   →  SELECT only")
    print("=" * 55)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=Config.DEBUG)
