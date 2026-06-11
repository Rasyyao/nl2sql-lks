# NL2SQL Agent — Pipeline Description

## Pipeline Overview

Setiap kali user mengirim pertanyaan via chat, pipeline berjalan melalui **11 langkah** dari input hingga response.

```
User Input: "Berapa total gaji dosen di Fakultas Teknik?"
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  Step 1: INTENT CLASSIFICATION (Cosine Similarity)  │
│  intent_classifier.classify(question)               │
│  → "SELECT" (confidence: 0.93)                      │
│  → mapped to: "data_query"                          │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────┴─────────┐
              │ Non-SQL Intent?  │
              └────────┬─────────┘
            YES ↙            ↘ NO
     ┌──────────────┐  ┌─────────────────────────────────────┐
     │ Return static │  │  Step 2: PREPROCESSING               │
     │ response      │  │  _preprocess_foto_update(question)   │
     │ (greeting,    │  │  → Detect photo update patterns      │
     │  schema info, │  └──────────────────┬──────────────────┘
     │  out_of_scope)│                     │
     └──────────────┘                     ▼
                       ┌─────────────────────────────────────┐
                       │  Step 3: SCHEMA RETRIEVAL (Cosine)   │
                       │  schema_retriever.get_relevant_schema│
                       │  (question, top_k=3)                 │
                       │  → Only dosen, remunerasi, fakultas  │
                       │  → ~200-300 tokens (vs ~900 full)    │
                       └──────────────────┬──────────────────┘
                                          │
                                          ▼
                       ┌─────────────────────────────────────┐
                       │  Step 4: PROMPT BUILDING             │
                       │  build_prompt(question, schema,      │
                       │              history_ctx)            │
                       │  → Schema + SQL rules + JOIN rules   │
                       │  → INSERT rules + name search rules  │
                       │  → Chat history context (last 6)     │
                       └──────────────────┬──────────────────┘
                                          │
                                          ▼
                       ┌─────────────────────────────────────┐
                       │  Step 5: LLM SQL GENERATION          │
                       │  ChatGroq/ChatAnthropic → SQL        │
                       │  clean_sql_output(raw)               │
                       │  _inject_auto_id(sql) (for INSERT)   │
                       └──────────────────┬──────────────────┘
                                          │
                                          ▼
                       ┌─────────────────────────────────────┐
                       │  Step 6: SQL VALIDATION              │
                       │  validate_sql_syntax(sql)            │
                       │  → Valid keyword? No multi-statement?│
                       └──────────────────┬──────────────────┘
                                          │
                                          ▼
                       ┌─────────────────────────────────────┐
                       │  Step 7: SECURITY GUARD              │
                       │  check_sql_permission(sql, role)     │
                       │  → Allowed? Needs confirm? Blocked?  │
                       └──────────────────┬──────────────────┘
                              │           │           │
                        Blocked     Needs Confirm  Allowed
                           │           │              │
                      Return error  Return SQL +      │
                                   ask confirm        │
                                                      ▼
                       ┌─────────────────────────────────────┐
                       │  Step 8: CACHE CHECK                 │
                       │  get_cached_result(sql)              │
                       │  → If cache hit: return cached data  │
                       └──────────────────┬──────────────────┘
                              │                    │
                         Cache HIT            Cache MISS
                            │                      │
                       Return cached               ▼
                       result              ┌─────────────────────────────────────┐
                                           │  Step 9: EXECUTE SQL                │
                                           │  execute_sql(sql, db_path)          │
                                           │  → Run on SQLite database           │
                                           └──────────────────┬──────────────────┘
                                                    │                   │
                                              SQL Error             Success
                                                    │                   │
                                                    ▼                   │
                                    ┌──────────────────────┐            │
                                    │  AUTO-REPAIR          │            │
                                    │  auto_repair_sql()    │            │
                                    │  → LLM fixes the SQL  │            │
                                    │  → Re-execute          │            │
                                    └───────────┬──────────┘            │
                                                │                       │
                                                ▼                       ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │  Step 10: POST-PROCESSING                               │
                       │                                                         │
                       │  ┌─ generate_natural_answer() → Bahasa Indonesia answer │
                       │  ├─ evaluate_sql() → Quality score (A-F)                │
                       │  ├─ detect_viz_intent() → Auto chart if requested       │
                       │  ├─ generate_insight() → AI data analysis               │
                       │  ├─ calculate_statistics() → Descriptive stats          │
                       │  ├─ check_data_quality() → Null/duplicate/outlier       │
                       │  └─ set_cached_result() → Cache SELECT results          │
                       └──────────────────────┬──────────────────────────────────┘
                                              │
                                              ▼
                       ┌─────────────────────────────────────┐
                       │  Step 11: RESPONSE & LOGGING         │
                       │                                      │
                       │  ├─ log_to_audit() → Audit trail     │
                       │  ├─ record_request() → Metrics       │
                       │  ├─ save_chat_message() → History    │
                       │  └─ JSONResponse(payload)            │
                       └──────────────────────────────────────┘
                                              │
                                              ▼
                                    JSON Response to Frontend
```

---

## Pipeline Step Details

### Step 1: Intent Classification

**File:** `intent_classifier.py` → `IntentClassifier.classify()`

```python
# Input
question = "Berapa total gaji dosen?"

# Process
query_vector = model.encode(question)          # 384-dim vector
similarities = prototypes_matrix @ query_vector # dot product
best_idx = argmax(similarities)                 # highest score

# Output
{"intent": "SELECT", "confidence": 0.93}
```

**Decision Flow:**
- `SELECT` → continue pipeline (generate SQL)
- `GREETING` → return greeting message, stop
- `SCHEMA_QUESTION` → return schema info, stop
- `EDUKASI_QUESTION` → return education page link, stop
- `OUT_OF_SCOPE` → return "di luar cakupan", stop
- `CLARIFICATION` → return "silakan perjelas", stop

### Step 2: Preprocessing

**File:** `agent.py` → `_preprocess_foto_update()`

Only activates for photo update queries. Transforms:
```
"update foto Bella dengan /foto/bella.jpg"
→ "UPDATE kolom foto pada tabel dosen: SET foto = '/foto/bella.jpg' WHERE nama_lengkap LIKE '%Bella%'"
```

### Step 3: Schema Retrieval

**File:** `schema_retrieval.py` → `SchemaRetriever.get_relevant_schema()`

```python
# Input
question = "total gaji dosen di fakultas teknik"

# Process
query_vec = model.encode(question)
similarities = table_embeddings @ query_vec
# dosen: 0.44, fakultas: 0.40, jabatan: 0.43, remunerasi: 0.50
top_3 = ["remunerasi", "dosen", "jabatan_fungsional"]

# Output: schema string with ONLY those 3 tables + FK relationships
```

### Step 4: Prompt Building

**File:** `agent.py` → `build_prompt()`

The prompt includes:
1. System role: "Kamu ahli SQL SQLite"
2. Output rules (no markdown, no explanation, one query only)
3. **Selected schema** (from step 3, not full schema)
4. JOIN rules with examples
5. WHERE vs HAVING rules
6. Name search rules (LIKE per token)
7. INSERT auto-ID rules
8. Chat history context (last 6 messages)
9. The user's question

### Step 5: LLM SQL Generation

**File:** `agent.py` → `generate_sql()` → `get_llm()`

```python
llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)
# or
llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)

raw_output = llm.invoke(prompt)
sql = clean_sql_output(raw_output)  # strip markdown, backticks
sql = _inject_auto_id(sql)          # add MAX+1 for INSERT PKs
```

### Step 6: SQL Validation

**File:** `guards.py` → `validate_sql_syntax()`

Checks:
- First keyword is valid (SELECT, INSERT, UPDATE, DELETE, etc.)
- No multiple statements (`;` followed by more SQL)

### Step 7: Security Guard

**File:** `guards.py` → `check_sql_permission()`

```python
# Demo mode: only SELECT allowed
# User role: only SELECT allowed
# Admin role: SELECT always, INSERT/UPDATE/DELETE needs confirmation
```

### Step 8: Cache Check

**File:** `query_cache.py` → `get_cached_result()`

- Only for SELECT queries
- Key: MD5 hash of normalized SQL
- TTL: 300 seconds (configurable)
- Cache invalidated after any INSERT/UPDATE/DELETE

### Step 9: Execute SQL

**File:** `utils.py` → `execute_sql()`

- Executes on SQLite database
- Returns `{success, columns, rows, rowcount, error}`
- If error → trigger auto-repair (LLM fixes SQL → re-execute)

### Step 10: Post-Processing

Runs multiple processors based on intent:

| Processor | When | Output |
|-----------|------|--------|
| `generate_natural_answer()` | Always | Human-readable Bahasa Indonesia answer |
| `evaluate_sql()` | Always | SQL quality score + grade (A-F) |
| `generate_chart()` | If viz keyword detected | Base64 PNG chart |
| `generate_insight()` | If intent = insight/report | AI-generated data insights |
| `calculate_statistics()` | If intent = statistic/report | Mean, median, std, min, max |
| `check_data_quality()` | If intent = data_quality | Null/duplicate/outlier report |

### Step 11: Response & Logging

Final JSON payload structure:
```json
{
    "question": "...",
    "sql": "SELECT ...",
    "answer": "Ditemukan 150 dosen...",
    "table": { "columns": [...], "rows": [...], "rowcount": 150 },
    "guard": { "allowed": true, "operation": "SELECT" },
    "optimization": { "score": 90, "grade": "A", "findings": [...] },
    "visualization": { "chart_type": "bar", "chart_b64": "..." },
    "insight": "Fakultas Teknik memiliki dosen terbanyak...",
    "statistics": { "gaji_pokok": { "rata_rata": 5000000, ... } },
    "meta": {
        "intent": "data_query",
        "source": "llm",
        "cache_hit": false,
        "auto_repaired": false,
        "model_id": "llama-3.3-70b-versatile",
        "token_usage": { "input_tokens": 450, "output_tokens": 35 }
    }
}
```

---

## Data Flow Diagram

```
┌──────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│  Browser  │───▶│  main.py     │───▶│  agent.py     │───▶│  Groq/Claude │
│  (chat UI)│    │  (FastAPI)   │    │  (NL2SQL core)│    │  (LLM API)   │
└──────────┘    └──────┬───────┘    └───────┬───────┘    └──────────────┘
                       │                    │
                       │        ┌───────────┼───────────┐
                       │        ▼           ▼           ▼
                       │  ┌──────────┐ ┌─────────┐ ┌──────────┐
                       │  │intent_   │ │schema_  │ │guards.py │
                       │  │classifier│ │retrieval│ │(security)│
                       │  └──────────┘ └─────────┘ └──────────┘
                       │        │           │
                       │        └─────┬─────┘
                       │              ▼
                       │     ┌─────────────────┐
                       │     │ sentence-        │
                       │     │ transformers     │
                       │     │ (all-MiniLM-L6)  │
                       │     └─────────────────┘
                       │
               ┌───────┼───────┐
               ▼       ▼       ▼
         ┌─────────┐ ┌──────┐ ┌────────────┐
         │universitas│ │audit │ │query_cache │
         │.db       │ │.db   │ │(in-memory) │
         └─────────┘ └──────┘ └────────────┘
```
