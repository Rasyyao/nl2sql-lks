# NL2SQL Agent

**AI Database Assistant Platform** — Terjemahkan pertanyaan bahasa natural menjadi SQL query secara otomatis, dengan antarmuka web yang lengkap, sistem keamanan berlapis, evaluasi kualitas query, analitik data, dan dukungan multi-model LLM.

---

## Daftar Isi

1. [Gambaran Umum](#gambaran-umum)
2. [Teknologi](#teknologi)
3. [Struktur Proyek](#struktur-proyek)
4. [Database Schema](#database-schema)
5. [Fitur Utama](#fitur-utama)
6. [API Endpoints](#api-endpoints)
7. [Keamanan & Autentikasi](#keamanan--autentikasi)
8. [Query Optimization Evaluation](#query-optimization-evaluation)
9. [Robustness Nama Siswa](#robustness-nama-siswa)
10. [Cara Menjalankan](#cara-menjalankan)
11. [Pengujian](#pengujian)
12. [Hasil Pengujian](#hasil-pengujian)

---

## Gambaran Umum

NL2SQL Agent mengubah pertanyaan bahasa Indonesia menjadi SQL query yang dieksekusi ke database SQLite. Pengguna cukup mengetik seperti bertanya kepada orang — sistem akan mengklasifikasi intent, menghasilkan SQL, memvalidasi, mengeksekusi, lalu menjawab dalam bahasa natural beserta insight, statistik, atau grafik sesuai kebutuhan.

```
User: "buatkan laporan nilai siswa kelas XII RPL 1"
         ↓
[Intent] → report (multi-step: data + insight + statistik + grafik)
         ↓
[LLM] → SELECT s.nama, m.nama, n.nilai FROM nilai_mapel n JOIN ...
         ↓
[Guard] → Validasi RBAC, demo mode, syntax
         ↓
[Execute] → SQLite → 30 baris hasil
         ↓
[Visualization] → bar chart nilai per mapel (base64 PNG)
         ↓
[Insight] → "Rata-rata kelas 78.4, Pemrograman Web tertinggi (84.2) ..."
         ↓
[Statistics] → mean/median/std/min/max per kolom numerik
         ↓
[Answer] → Jawaban bahasa Indonesia + tabel + grafik + insight
         ↓
[Optimizer] → Score: 95/100, Grade A
```

---

## Teknologi

| Komponen | Teknologi |
|---|---|
| Web Framework | FastAPI 0.111 + Uvicorn |
| LLM — Groq | llama-3.1-8b-instant, llama-3.3-70b-versatile |
| LLM — Anthropic | claude-sonnet-4-6, claude-haiku-4-5-20251001 |
| LangChain | langchain 0.2.16 + langchain-groq + langchain-anthropic |
| Database | SQLite (school.db + audit.db) |
| Auth | JWT (python-jose) + Cookie httponly |
| Template | Jinja2 + Tailwind CSS CDN |
| Data Analysis | Pandas 2.2 (statistik & quality check) |
| Visualisasi | Matplotlib + Seaborn (dark theme, base64 PNG) |
| Export | openpyxl (Excel) + csv (CSV) + printable HTML (PDF) |
| Password | Werkzeug password hashing |

---

## Struktur Proyek

```
nl2sql-fastapi/
├── main.py              # Entry point FastAPI — 22 endpoints
├── agent.py             # Pipeline NL2SQL: intent → SQL → answer + analytics
├── auth.py              # JWT auth, dual cookie+Bearer support
├── guards.py            # RBAC guard, demo mode, syntax validator
├── utils.py             # Schema cache, SQL executor, audit log, export, upload
├── query_cache.py       # TTL cache in-memory untuk SELECT (5 menit)
├── query_optimizer.py   # Query Optimization Rate Evaluation (15 aturan)
├── observability.py     # Metrik performa request
├── schema_summary.py    # Schema formatter untuk LLM prompt
├── visualizer.py        # Chart generator: bar/line/pie (matplotlib, dark theme)
├── database_setup.py    # Inisialisasi school.db + audit.db
├── config.py            # Konfigurasi dari .env (4 model, 2 provider)
├── requirements.txt
├── .env                 # GROQ_API_KEY, ANTHROPIC_API_KEY, SECRET_KEY
│
├── templates/
│   ├── layout.html           # Base template navbar + style
│   ├── login.html            # Halaman login
│   ├── chat.html             # Antarmuka chat utama (insight/stats/quality/report)
│   ├── admin_dashboard.html  # Dashboard audit log, metrik, user, optimization
│   └── edukasi.html          # Halaman edukasi fitur sistem
│
├── static/
│   └── tailwind.css
│
├── test_nl2sql.py       # 52 test case (SELECT/UPDATE/INSERT/DELETE/DROP/SECURITY/EDGE)
├── test_nl2sql2.py      # 12 test case (HAVING fix + agregasi kompleks)
└── testnama.py          # 46 test case robustness nama (typo/ambigu/parsial)
```

---

## Database Schema

### `school.db` — Database Utama

```
siswa          kelas          mapel          nilai_mapel
──────────     ──────────     ──────────     ──────────────
id (PK)        id (PK)        id (PK)        id (PK)
nama           nama           nama           siswa_id (FK)
nis            jurusan        kode           mapel_id (FK)
gender         wali           kkm            nilai
kelas_id (FK)                               semester
alamat                                       tahun_ajaran
tanggal_masuk
```

**Data awal:** 15 siswa, 5 kelas, 6 mata pelajaran, 90 nilai (seed=42)

**Mata pelajaran:** Pemrograman Web, Basis Data, PBO, Matematika, Bahasa Indonesia, Bahasa Inggris

### `audit.db` — Database Sistem

```
users                    audit_log              metrics_log
─────────────────        ─────────────────      ────────────
id, username             id, username           id
password_hash            role, pertanyaan       sql_gen_ms
name, role               sql_query              exec_ms
active                   status, pesan          success, blocked
created_at               waktu                  created_at

query_optimization_log
──────────────────────
id, username, question
sql_query, score, grade
findings_json, created_at
```

---

## Fitur Utama

### 1. Classifier 9-Intent

Setiap pertanyaan diklasifikasi ke salah satu dari 9 intent sebelum masuk pipeline:

| Intent | Trigger Contoh | Perilaku |
|---|---|---|
| `greeting` | "halo", "hai", "assalamu" | Jawaban sambutan, tanpa SQL |
| `schema_question` | "tabel apa saja", "kolom apa" | Tampilkan skema database |
| `edukasi_question` | "bagaimana sistem ini" | Redirect ke halaman edukasi |
| `report` | "buatkan laporan", "laporan data" | SQL + insight + statistik + grafik |
| `comparison` | "bandingkan", " vs " | SQL + insight perbandingan |
| `data_quality` | "data aneh", "ada null", "outlier" | SQL + quality check + skor |
| `statistic` | "standar deviasi", "statistik deskriptif" | SQL + mean/median/std/min/max |
| `visualization` | "grafik", "chart", "plot" | SQL + auto-chart |
| `insight` | "insight", "jelaskan data", "pola data" | SQL + LLM insight bullets |
| `data_query` | (default) | SQL + jawaban natural |

**Multi-step detection:** Pertanyaan yang memicu 2+ kelompok fitur (contoh: "tampilkan grafik dan jelaskan datanya") otomatis diklasifikasi ke `report` dan menjalankan semua post-processor.

### 2. NL2SQL Pipeline (10 Langkah)

```
 1. Intent Classification  → 9 intent (non-SQL short-circuit sebelum LLM)
 2. SQL Generation (LLM)   → Groq / Anthropic via LangChain (+ context memory)
 3. Syntax Validation      → keyword check, multi-statement guard
 4. RBAC Guard             → role user/admin, demo mode
 5. Cache Check            → TTL 5 menit untuk SELECT
 6. EXPLAIN QUERY PLAN     → sandbox/edukasi
 7. Execute SQL            → SQLite
 8. Auto-Repair            → jika error, LLM perbaiki otomatis
 9. Natural Answer         → jawaban bahasa Indonesia
10. Query Optimization     → evaluasi kualitas SQL (score 0-100)
    + Name Mismatch Guard  → cegah false match nama
    + Partial Name Suggest → saran nama lengkap jika parsial
    ── POST-PROCESSORS (berdasarkan intent) ──────────────
    + Data Visualization   → bar/line/pie chart (matplotlib)
    + Data Insight         → 3-4 bullet insight dari LLM
    + Statistical Helper   → mean/median/std/min/max (pandas)
    + Data Quality Check   → null/duplikat/outlier + skor 0-100
    + Report Composer      → gabung semua komponen jadi laporan
```

### 3. Multi-Model LLM

Ganti model secara real-time dari UI chat tanpa restart server:

| Model | Provider | Keunggulan |
|---|---|---|
| `llama-3.1-8b-instant` | Groq | Cepat, ringan, default |
| `llama-3.3-70b-versatile` | Groq | Akurasi SQL kompleks lebih tinggi |
| `claude-sonnet-4-6` | Anthropic | Terbaik untuk insight & laporan |
| `claude-haiku-4-5-20251001` | Anthropic | Cepat + hemat, kualitas baik |

### 4. Follow-up Context Memory

Riwayat percakapan (12 pesan terakhir) dikirim bersama setiap request. LLM memahami konteks lanjutan:

```
User: "tampilkan nilai kelas XII RPL 1"
AI:   [tabel nilai]
User: "urutkan dari yang tertinggi"   ← LLM tahu "yang" = kelas XII RPL 1
AI:   [tabel nilai, sorted DESC]
```

### 5. Data Insight Generator

Intent `insight`, `comparison`, `report` → LLM membaca ringkasan DataFrame dan menghasilkan 3-4 bullet insight bahasa Indonesia (pola, anomali, rekomendasi).

### 6. Statistical Helper

Intent `statistic`, `report` → pandas menghitung per kolom numerik:

| Kolom | mean | median | std | min | max |
|---|---|---|---|---|---|
| nilai | 78.4 | 79.0 | 8.2 | 55 | 98 |

Tidak menggunakan LLM — murni pandas, deterministik.

### 7. Comparison Mode

Intent `comparison` → SQL mengambil data dua entitas, insight LLM menjelaskan perbandingan, jawaban di-override dengan narasi perbandingan.

### 8. Report Generator (PDF)

Intent `report` → gabungkan semua komponen:
- Tabel data hasil SQL
- Grafik (bar/line/pie)
- Insight AI
- Statistik deskriptif
- SQL query yang digunakan

Export ke PDF via tombol **PDF Report** → server render HTML siap cetak → browser print dialog.

### 9. Anomaly & Data Quality Checker

Intent `data_quality` → pandas memeriksa:

| Jenis | Metode |
|---|---|
| Missing value | `df.isnull()` per kolom |
| Duplikat | `df.duplicated()` |
| Outlier numerik | IQR method (Q1−1.5×IQR / Q3+1.5×IQR) |

Hasilkan **Quality Score 0-100** dengan grade A/B/C/D/F.

### 10. Auto Data Visualization

Intent `visualization`, `comparison`, `report`, atau pertanyaan mengandung kata kunci grafik → matplotlib auto-generate chart:

- Pilih tipe (bar, line, pie) berdasarkan data
- Dark theme, ukuran responsif
- Return sebagai base64 PNG, langsung tampil di chat

### 11. Chat Interface

- Input pertanyaan bahasa natural Indonesia
- **Transparency Panel** — langkah pipeline: Intent, SQL, EXPLAIN, Hasil, Optimization Score, Insight, Statistik, Quality
- Tabel hasil query yang dapat di-export
- Konfirmasi untuk operasi berbahaya (UPDATE/DELETE/DROP)
- Export ke CSV, Excel, dan PDF Report
- Selector model LLM (4 model, 2 provider)

### 12. RBAC (Role-Based Access Control)

| Role | SQL | Analitik | Upload DB |
|---|---|---|---|
| `admin` | SELECT + DML (konfirmasi) | Semua | Ya |
| `user` | SELECT saja | Semua | Ya |

### 13. Demo Mode

Admin dapat mengaktifkan Demo Mode yang memblok semua operasi non-SELECT — berguna saat presentasi atau demo publik.

### 14. Admin Dashboard

Tab yang tersedia:

- **Audit Log** — riwayat semua query dengan status (executed/blocked/error)
- **Optimization** — statistik kualitas SQL, grade distribution, riwayat evaluasi
- **Manajemen User** — tambah user baru (admin/user)
- **System Info** — metrik performa, cache stats, uptime

### 15. Schema Detection & Upload

- Schema database dibaca otomatis saat startup dan dijadikan bagian prompt LLM
- Upload file `.db` (SQLite) untuk ganti database aktif per-user
- Upload file `.csv` untuk import ke tabel baru
- Schema di-reload otomatis setelah upload

### 16. Query Cache

Hasil SELECT di-cache 5 menit (in-memory, per-proses). Cache di-invalidate otomatis saat ada operasi write (INSERT/UPDATE/DELETE).

---

## API Endpoints

### Halaman HTML

| Method | Path | Keterangan |
|---|---|---|
| GET | `/` | Halaman login |
| POST | `/login` | Login via HTML form |
| GET | `/logout` | Logout, hapus cookie |
| GET | `/chat` | Halaman chat utama |
| GET | `/admin` | Admin dashboard (admin only) |
| GET | `/edukasi` | Halaman edukasi fitur |

### API

| Method | Path | Auth | Keterangan |
|---|---|---|---|
| POST | `/api/auth/login` | — | Login, return Bearer token |
| POST | `/api/ask` | ✓ | Pipeline NL2SQL utama |
| POST | `/api/clear-history` | ✓ | Clear chat history |
| GET | `/api/schema` | ✓ | Info schema database |
| POST | `/api/reload-schema` | ✓ | Reload schema cache |
| GET | `/api/models` | ✓ | Daftar model tersedia + status aktif |
| POST | `/api/model/switch` | ✓ | Ganti model aktif |
| POST | `/api/demo-mode` | admin | Toggle demo mode |
| GET | `/api/demo-mode/status` | ✓ | Status demo mode |
| POST | `/api/export/csv` | ✓ | Export hasil ke CSV |
| POST | `/api/export/excel` | ✓ | Export hasil ke Excel |
| POST | `/api/export/report` | ✓ | Generate laporan HTML (print → PDF) |
| POST | `/api/upload-db` | ✓ | Upload database/CSV |
| GET | `/api/audit-logs` | admin | Riwayat audit |
| GET | `/api/metrics` | admin | Metrik performa |
| GET | `/api/optimization/stats` | admin | Statistik optimasi |
| GET | `/api/optimization/history` | admin | Riwayat evaluasi |
| POST | `/api/add-user` | admin | Tambah user baru |

> Dokumentasi interaktif tersedia di **`/docs`** (Swagger UI otomatis dari FastAPI)

### Autentikasi Ganda

API mendukung dua cara autentikasi:
- **Cookie** `access_token` — untuk browser dan JS fetch
- **Bearer token** di header `Authorization` — untuk test runner dan API client

---

## Keamanan & Autentikasi

### JWT Token

- Algorithm: HS256
- Expire: 8 jam
- Disimpan: cookie httponly (browser) atau Bearer header (API)

### Guard Berlapis

```
1. Syntax Guard     → validasi keyword SQL, cegah multiple statements
2. RBAC Guard       → cek role, blok operasi berbahaya untuk 'user'
3. Demo Mode Guard  → blok semua non-SELECT saat demo
4. Name Guard       → deteksi LLM mengganti nama user (false match prevention)
```

### Name Mismatch Guard

Mencegah LLM secara diam-diam mengoreksi nama yang diketik user:

```
User: "Tampilkan nilai Budo Santoso"
LLM SQL: WHERE nama = 'Budi Santoso'  ← BERBEDA!

Guard: similarity(Budo, Budi) = 0.92 > threshold
→ Blok hasil, tampilkan peringatan ke user
```

---

## Query Optimization Evaluation

Setiap SQL yang berhasil dieksekusi langsung dievaluasi kualitasnya. Hasil muncul di **Step 6** Transparency Panel.

### 15 Aturan Evaluasi

| Kode | Nama | Kategori | Penalti |
|---|---|---|---|
| S01 | SELECT * | Structural | -10 |
| S02 | Implicit JOIN | Structural | -15 |
| S03 | Tanpa alias tabel | Structural | -5 |
| S04 | Multiple statements | Structural | -30 |
| P01 | LIKE leading wildcard | Performance | -10 |
| P02 | IN (SELECT...) vs JOIN | Performance | -8 |
| P03 | DISTINCT berlebih | Performance | -5 |
| P04 | Fungsi pada kolom WHERE | Performance | -8 |
| P05 | ORDER BY tanpa LIMIT | Performance | -5 |
| C01 | HAVING tanpa GROUP BY | Correctness | -20 |
| C02 | COUNT(*) vs COUNT(col) | Correctness | -3 |
| C03 | GROUP BY tidak konsisten | Correctness | -12 |
| B01 | Tabel tanpa alias (3+ JOIN) | Best Practice | -5 |
| B02 | Magic number | Best Practice | -2 |
| B03 | Correlated subquery | Best Practice | -8 |

### Scoring

```
Score = 100 - total_penalti
Grade A: 90-100  Grade B: 80-89  Grade C: 70-79  Grade D: 60-69  Grade F: <60
```

### Contoh Evaluasi

```sql
-- Grade A (100/100): Query optimal
SELECT s.nama, ROUND(AVG(n.nilai), 2) AS rata_rata
FROM nilai_mapel n
JOIN siswa s ON n.siswa_id = s.id
GROUP BY s.id
HAVING AVG(n.nilai) < 78
ORDER BY rata_rata DESC
LIMIT 5

-- Grade B (85/100): Ada implicit JOIN
SELECT s.nama FROM siswa s, nilai_mapel n  -- -15 S02
WHERE s.id = n.siswa_id
```

---

## Robustness Nama Siswa

Sistem dilengkapi mekanisme khusus untuk menangani kesalahan nama:

### Masalah yang Ditangani

| Jenis | Contoh | Penanganan |
|---|---|---|
| Typo ringan | Budo → Budi | Name Mismatch Guard memblok |
| Huruf tertukar | Adni Saputra | Guard memblok auto-koreksi LLM |
| Nama mirip | Andi Saputro vs Andi Saputra | Guard memblok fuzzy matching |
| Nama tidak ada | Bambang Supriyadi | SQL return 0 rows, jawaban "tidak ditemukan" |
| Nama parsial | "Siti" | Suggestion: "Maksud Anda: Siti Rahayu, Siti Rahaya?" |
| Nama ambigu | "Kevin" | Suggestion: "Kevin Pratama, Kevin Pratomo?" |

### Partial Name Suggestion

Saat user menyebut nama parsial (1 kata) dan hasil 0 baris, sistem mencari nama mirip di database dan menawarkan saran:

```
User: "Tampilkan nilai Kevin"
→ SQL: WHERE nama = 'Kevin'  → 0 rows
→ Sistem: "Apakah yang Anda maksud: 'Kevin Pratama', 'Kevin Pratomo'?
           Silakan coba dengan nama lengkap."
```

---

## Cara Menjalankan

### Prasyarat

- Python 3.10+
- Groq API Key — gratis di [console.groq.com](https://console.groq.com)
- Anthropic API Key (opsional) — untuk model Claude di [console.anthropic.com](https://console.anthropic.com)

### Instalasi

```bash
# Clone atau ekstrak project
cd nl2sql-fastapi

# Buat virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Konfigurasi .env
cp .env.example .env
# Edit .env → isi API key
```

### Konfigurasi `.env`

```env
GROQ_API_KEY=gsk_your_key_here
ANTHROPIC_API_KEY=sk-ant-your_key_here   # opsional, untuk model Claude
SECRET_KEY=ganti-dengan-string-acak-panjang
DATABASE_PATH=school.db
AUDIT_DB_PATH=audit.db
DEFAULT_MODEL=llama-3.1-8b-instant
```

### Menjalankan

```bash
# Cara 1 — langsung
python main.py

# Cara 2 — uvicorn dengan auto-reload
uvicorn main:app --reload --port 8000
```

Buka browser: `http://localhost:8000`

| Akun | Password | Akses |
|---|---|---|
| `admin` | `admin123` | Full access + admin dashboard |
| `user` | `user123` | SELECT only |

**API Docs (Swagger UI):** `http://localhost:8000/docs`

---

## Pengujian

Tiga modul test runner tersedia. Semua menghasilkan file log yang dapat dikirim untuk review.

### `test_nl2sql.py` — Test SQL Umum

```bash
python test_nl2sql.py
# Output: test_results_LOG.txt
```

**52 test case**, mencakup:

| Grup | Jumlah | Deskripsi |
|---|---|---|
| SELECT | 31 | Query sederhana hingga agregasi kompleks |
| UPDATE | 6 | Update nilai dengan subquery |
| INSERT | 3 | Insert dengan subquery |
| DELETE | 3 | Delete dengan filter |
| DROP | 1 | Harus munculkan konfirmasi, tidak dieksekusi |
| SECURITY | 2 | Operasi berbahaya harus diblok untuk role user |
| EDGE | 6 | Greeting, schema question, pertanyaan ambigu |

Level kesulitan: EASY (15) · MEDIUM (15) · HARD (22)

### `test_nl2sql2.py` — Test HAVING & Agregasi

```bash
python test_nl2sql2.py
# Output: test_results_LOG2.txt
```

**12 test case** fokus pada:

| Grup | Jumlah | Deskripsi |
|---|---|---|
| HAVING_FIX | 5 | WHERE vs HAVING — bug kritis yang telah diperbaiki |
| SELECT_HARD | 5 | MAX per mapel, subquery global, perbandingan kelas |
| UPDATE_HARD | 1 | UPDATE increment dengan filter kelas |
| SELECT_MEDIUM | 1 | Verifikasi hasil UPDATE |

Script ini **mereset database otomatis** sebelum test (data seed=42) dan me-reload schema cache.

### `testnama.py` — Test Robustness Nama

```bash
python testnama.py
# Output: test_results_nama.txt
```

**46 test case** otomatis dari nama di database:

| Level | Subtype | Jumlah | Deskripsi |
|---|---|---|---|
| Easy | exact_match | 8 | Nama persis dari DB |
| Easy | not_exist | 6 | Nama yang tidak ada di DB |
| Medium | typo | 16 | Variasi typo otomatis (ganti huruf, tertukar, hilang, spasi) |
| Hard | ambiguous | 8 | Nama di antara dua nama mirip di DB |
| Hard | partial_name | 8 | Nama depan / nama belakang saja |

Script ini **menambahkan 5 siswa baru** dengan nama mirip untuk membuat skenario ambigu:

| ID | Nama Baru | Mirip Dengan |
|---|---|---|
| 16 | Andi Saputri | Andi Saputra |
| 17 | Siti Rahaya | Siti Rahayu |
| 18 | Kevin Pratomo | Kevin Pratama |
| 19 | Jeni Susanto | Jeni Susanti |
| 20 | Lina Marliani | Lina Marlinda + Rina Marlina |

---

## Hasil Pengujian

### `test_nl2sql.py` — Hasil Final

```
Total : 52 test cases
PASS  : 49/52 (94.2%)
```

| Grup | Hasil |
|---|---|
| SELECT | 29/31 (94%) |
| UPDATE | 6/6 (100%) |
| INSERT | 2/3 (67%) — T33 intentional skip |
| DELETE | 3/3 (100%) |
| DROP | 1/1 (100%) |
| SECURITY | 2/2 (100%) |
| EDGE | 6/6 (100%) |

### `test_nl2sql2.py` — Hasil Final

```
Total : 12 test cases
PASS  : 12/12 (100%) ✅
```

Semua kasus HAVING, agregasi kompleks, dan subquery berhasil.

Key fix yang diterapkan selama iterasi:
- HAVING vs WHERE: LLM kini selalu pakai `HAVING AVG(n.nilai) < X` untuk filter rata-rata
- Correlated subquery: subquery global menggunakan `(SELECT AVG(nilai) FROM nilai_mapel)` tanpa alias
- MAX per mapel: `GROUP BY n.mapel_id` bukan `ORDER BY DESC LIMIT 1`
- ORDER ASC LIMIT tanpa HAVING untuk ranking

### `testnama.py` — Hasil Final

```
Total         : 46 test cases
PASS          : 46/46 (100%) ✅
false_match   : 0
```

| Level | Hasil |
|---|---|
| EASY | 14/14 (100%) |
| MEDIUM | 16/16 (100%) |
| HARD | 16/16 (100%) |

| Subtype | Hasil |
|---|---|
| exact_match | 8/8 (100%) |
| not_exist | 6/6 (100%) |
| typo | 16/16 (100%) — semua typo tidak false match |
| ambiguous | 8/8 (100%) — nama ambigu ditangani dengan benar |
| partial_name | 8/8 (100%) — suggestion muncul, dideteksi sebagai ambiguous |

---

## Kontribusi Iteratif

Proyek ini dikembangkan secara iteratif melalui siklus: **test → analisis log → perbaikan prompt/guard/pipeline → test ulang**. Setiap test log yang dikirim menghasilkan perbaikan spesifik yang terukur dan terdokumentasi.

---

*NL2SQL Agent v3.0 — FastAPI Edition*
