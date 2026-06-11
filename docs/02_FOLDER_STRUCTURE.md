# NL2SQL Agent — Folder Structure & File Functions

## Directory Tree

```
LKS AI/
├── main.py                  ← FastAPI app entry point (routes + pipeline orchestrator)
├── agent.py                 ← NL2SQL core: intent → schema → LLM → SQL
├── intent_classifier.py     ← Semantic intent classification (sentence-transformers)
├── schema_retrieval.py      ← Smart schema retrieval (top-K tables via embeddings)
├── schema_summary.py        ← Legacy full schema string (superseded by schema_retrieval)
├── guards.py                ← SQL permission & security guard
├── query_cache.py           ← MD5-based query result cache with TTL
├── query_optimizer.py       ← SQL quality evaluator (score, grade, suggestions)
├── visualizer.py            ← Auto chart generation (matplotlib/seaborn)
├── config.py                ← Centralized configuration from .env
├── auth.py                  ← JWT authentication + user management
├── database_setup.py        ← Audit/auth database table initialization
├── utils.py                 ← DB execution, audit logging, export, chat history
├── observability.py         ← Request metrics + performance timer
├── requirements.txt         ← Python dependencies
├── .env                     ← Environment variables (API keys, DB path)
├── universitas_lks_*.db     ← SQLite database (data universitas)
├── universitas_lks_*.sql    ← SQL dump for recreating the database
├── audit.db                 ← SQLite database (audit logs, users, chat history)
├── test_upgrade.py          ← Test script for intent classifier + schema retrieval
│
├── static/                  ← CSS, JS, images, favicon
├── templates/               ← Jinja2 HTML templates
│   ├── login.html
│   ├── chat.html
│   ├── admin_dashboard.html
│   └── panduan.html
├── foto/                    ← Uploaded lecturer photos
├── uploads/                 ← Uploaded DB/CSV files
└── venv/                    ← Python virtual environment
```

---

## File-by-File Description

### 🔵 Core Pipeline Files

---

#### `main.py` — FastAPI App & Route Handlers
**Lines:** ~986 | **Role:** Entry point, HTTP routes, pipeline orchestration

**Key Functions:**
| Function | Description |
|----------|-------------|
| `startup()` | App startup: init databases, load schema cache, setup tables |
| `api_ask()` | Main endpoint `POST /api/ask` — receives user question, runs full pipeline |
| `_run_pipeline()` | Core pipeline: validate → guard → cache → explain → execute → answer |
| `_error_response()` | Standardized error response builder |
| `_check_name_mismatch()` | Detect if LLM hallucinated a name not in user's question |
| `_suggest_similar_names()` | Suggest similar names when exact match fails |

**API Routes:**
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Login page |
| `POST` | `/login` | Form login → set JWT cookie |
| `GET` | `/logout` | Clear JWT cookie |
| `GET` | `/chat` | Chat UI page |
| `GET` | `/admin` | Admin dashboard |
| `GET` | `/panduan` | Education/guide page |
| `POST` | `/api/ask` | **Main NL2SQL endpoint** |
| `POST` | `/api/clear-history` | Clear chat history |
| `GET` | `/api/chat-history` | Get chat history |
| `GET` | `/api/models` | List available LLM models |
| `POST` | `/api/model/switch` | Switch active LLM model |
| `GET` | `/api/schema` | Get database schema |
| `POST` | `/api/reload-schema` | Reload schema cache |
| `POST` | `/api/demo-mode` | Toggle demo mode (admin only) |
| `POST` | `/api/export/csv` | Export query results to CSV |
| `POST` | `/api/export/excel` | Export query results to Excel |
| `POST` | `/api/export/report` | Generate HTML report |
| `POST` | `/api/upload/foto` | Upload lecturer photo |
| `GET` | `/api/audit-logs` | View audit logs (admin only) |
| `GET` | `/api/metrics` | View performance metrics (admin only) |
| `POST` | `/api/add-user` | Add new user (admin only) |

---

#### `agent.py` — NL2SQL Agent Core
**Lines:** ~837 | **Role:** Intent classification, SQL generation, natural language answers

**Key Functions:**
| Function | Description |
|----------|-------------|
| `get_llm()` | Create LLM instance (Groq or Anthropic based on active model) |
| `classify_intent(question)` | Classify user intent via cosine similarity → pipeline intent name |
| `handle_non_sql(intent)` | Return response for non-SQL intents (greeting, schema, etc.) |
| `build_prompt(question, schema, history_ctx)` | Build the LLM prompt with schema + rules + question |
| `generate_sql(question, chat_history)` | **Main function**: classify → schema → prompt → LLM → SQL |
| `auto_repair_sql(question, broken_sql, error)` | Send failed SQL back to LLM for repair |
| `clean_sql_output(raw)` | Strip markdown/backticks from LLM output |
| `generate_natural_answer(question, sql, result)` | Generate human-readable answer from SQL results |
| `generate_insight(question, columns, rows)` | LLM-powered data analysis (3-4 insights) |
| `calculate_statistics(columns, rows)` | Descriptive statistics (mean, median, std, min, max) |
| `check_data_quality(columns, rows)` | Check for null values, duplicates, outliers |
| `explain_sql_error_friendly(question, sql, error)` | LLM explains SQL error in simple language |
| `set_active_model(model_id)` | Switch active LLM model |
| `_inject_auto_id(sql)` | Auto-insert MAX+1 PK for INSERT queries |
| `_preprocess_foto_update(question)` | Preprocess photo update questions |

---

#### `intent_classifier.py` — Semantic Intent Classification
**Lines:** ~250 | **Role:** Classify user query into 6 intents using sentence-transformer embeddings

**How it works:**
1. At startup: load `all-MiniLM-L6-v2` model → embed 83 prototype sentences
2. At runtime: embed user query → cosine similarity (dot product) → pick best intent

**Class: `IntentClassifier`**
| Method | Description |
|--------|-------------|
| `__init__(model_name, threshold, model)` | Load model, embed all prototypes |
| `classify(query, threshold)` | Returns `{"intent": str, "confidence": float}` |
| `classify_top_k(query, k)` | Returns top-K matches with matched prototype |

**Intents Supported:**
| Intent | Example | Pipeline Mapping |
|--------|---------|-----------------|
| `SELECT` | "tampilkan semua dosen" | `data_query` |
| `GREETING` | "halo", "selamat pagi" | `greeting` |
| `OUT_OF_SCOPE` | "siapa presiden indonesia" | `out_of_scope` |
| `CLARIFICATION` | "maksudnya apa" | `clarification` |
| `SCHEMA_QUESTION` | "tabel apa saja" | `schema_question` |
| `EDUKASI_QUESTION` | "apa itu nl2sql" | `edukasi_question` |

**Module Singleton:** `intent_classifier` — loaded once at import time

---

#### `schema_retrieval.py` — Smart Schema Retrieval
**Lines:** ~288 | **Role:** Retrieve only relevant table schemas instead of injecting full schema

**How it works:**
1. At startup: embed table descriptions (name + columns + purpose)
2. At runtime: embed user query → cosine similarity → pick top-K tables → format schema

**Class: `SchemaRetriever`**
| Method | Description |
|--------|-------------|
| `__init__(model, model_name)` | Embed all 4 table descriptions |
| `get_relevant_table_names(query, top_k)` | Returns `List[str]` of table names |
| `get_relevant_schema(query, top_k)` | Returns formatted schema string for LLM |
| `get_similarities(query)` | Debug: returns similarity scores per table |

**Module Singleton:** `schema_retriever` — shares model with `intent_classifier`

---

### 🟢 Security & Infrastructure

---

#### `guards.py` — SQL Security Guard
**Lines:** ~92 | **Role:** Permission checking based on role + demo mode

| Function | Description |
|----------|-------------|
| `check_sql_permission(sql, role)` | Check if SQL operation is allowed for given role |
| `validate_sql_syntax(sql)` | Basic validation: valid keyword start, no multi-statement |
| `set_demo_mode(enabled)` | Toggle demo mode (SELECT-only) |
| `is_demo_mode()` | Check if demo mode is active |

**Permission Matrix:**
| Role | SELECT | INSERT/UPDATE/DELETE | DROP/ALTER |
|------|--------|---------------------|------------|
| user | ✅ | ❌ | ❌ |
| admin | ✅ | ✅ (needs confirm) | ✅ (needs confirm) |
| demo mode | ✅ | ❌ | ❌ |

---

#### `query_cache.py` — Query Result Cache
**Lines:** ~41 | **Role:** Cache SELECT results using MD5 hash with TTL

| Function | Description |
|----------|-------------|
| `get_cached_result(sql)` | Lookup cache by MD5 hash |
| `set_cached_result(sql, result)` | Cache SELECT results |
| `invalidate_cache()` | Clear entire cache (after INSERT/UPDATE/DELETE) |
| `get_cache_stats()` | Return cache statistics |

---

#### `auth.py` — Authentication & User Management
**Lines:** ~169 | **Role:** JWT-based auth, user CRUD

| Function | Description |
|----------|-------------|
| `setup_user_database()` | Create users table, seed default admin/user |
| `create_access_token(username, role, name)` | Generate JWT token (8h expiry) |
| `verify_credentials(username, password)` | Verify login credentials |
| `get_current_user(request)` | FastAPI dependency: extract user from JWT |
| `require_admin(user)` | FastAPI dependency: require admin role |
| `get_user_from_cookie(request)` | Extract user from httponly cookie |
| `get_all_users()` | List all users |
| `add_user(username, password, name, role)` | Create new user |

---

#### `config.py` — Configuration
**Lines:** ~78 | **Role:** Load settings from `.env` file

| Setting | Description |
|---------|-------------|
| `GROQ_API_KEY` | Groq API key for Llama models |
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude models |
| `DATABASE_PATH` | Path to university SQLite database |
| `AUDIT_DB_PATH` | Path to audit SQLite database |
| `AVAILABLE_MODELS` | Dict of all available LLM models |
| `DEFAULT_MODEL` | Default LLM model ID |
| `DANGEROUS_OPERATIONS` | List of operations requiring confirmation |
| `DEMO_MODE_DEFAULT` | Whether demo mode is on by default |

---

### 🟡 Utility & Processing Files

---

#### `utils.py` — Database Utilities
**Lines:** ~246 | **Role:** SQL execution, schema cache, audit logging, export, chat history

| Function | Description |
|----------|-------------|
| `load_schema_to_cache(db_path)` | Load table schemas into memory cache |
| `execute_sql(sql, db_path)` | Execute SQL on SQLite database |
| `run_explain_query(sql, db_path)` | Run EXPLAIN QUERY PLAN |
| `log_to_audit(...)` | Log query to audit_log table |
| `get_audit_logs(limit)` | Retrieve audit logs |
| `export_to_csv(columns, rows)` | Export to CSV string |
| `export_to_excel(columns, rows)` | Export to Excel bytes |
| `save_chat_message(...)` | Save chat message to database |
| `get_chat_history(username, limit)` | Get chat history for user |
| `clear_chat_history(username)` | Delete user's chat history |

---

#### `query_optimizer.py` — SQL Quality Evaluator
**Lines:** ~474 | **Role:** Score and grade SQL quality (A-F), detect anti-patterns

**13 Rules checked:**
| Rule | Category | Penalty | Description |
|------|----------|---------|-------------|
| S01 | structural | 10 | SELECT * usage |
| S02 | structural | 15 | Implicit JOIN |
| S03 | structural | 5 | Missing table alias |
| S04 | structural | 30 | Multiple statements |
| P01 | performance | 10 | Leading wildcard LIKE |
| P02 | performance | 8 | IN subquery vs JOIN |
| P03 | performance | 5 | Unnecessary DISTINCT |
| P04 | performance | 8 | Function on WHERE column |
| P05 | performance | 5 | ORDER BY without LIMIT |
| C01 | correctness | 20 | HAVING without GROUP BY |
| C02 | correctness | 3 | COUNT(*) vs COUNT(col) |
| C03 | correctness | 12 | Inconsistent GROUP BY |
| B01-B03 | best_practice | 2-8 | Various best practices |

---

#### `visualizer.py` — Chart Generator
**Lines:** ~620 | **Role:** Auto-generate charts from SQL results

| Function | Description |
|----------|-------------|
| `detect_viz_intent(question)` | Check if user wants a visualization |
| `suggest_chart_type(columns, rows, question)` | Pick best chart type based on data shape |
| `generate_chart(columns, rows, question)` | Main entry: auto-generate chart as base64 PNG |

**Chart Types:** bar, barh, pie, line, scatter, bar_multi, bar_grouped, histogram, box

---

#### `observability.py` — Metrics & Timer
**Lines:** ~74 | **Role:** Track request counts, latency, error rates

| Function/Class | Description |
|----------------|-------------|
| `Timer` | Context manager for timing operations |
| `record_request(...)` | Record a request with all its metrics |
| `get_metrics()` | Return aggregated metrics (avg latency, error rate, etc.) |

---

#### `database_setup.py` — Database Initialization
**Lines:** ~88 | **Role:** Create audit/auth tables on first run

Creates these tables in `audit.db`:
- `audit_log` — query audit trail
- `query_history` — query history
- `metrics_log` — performance metrics
- `users` — user accounts
- `chat_history` — chat messages

---

#### `schema_summary.py` — Legacy Full Schema
**Lines:** ~44 | **Role:** Returns hardcoded full schema string (superseded by `schema_retrieval.py`)

> ⚠️ **Deprecated**: This file is kept for backward compatibility but is no longer imported by `agent.py`. The new `schema_retrieval.py` replaces it with semantic top-K retrieval.
