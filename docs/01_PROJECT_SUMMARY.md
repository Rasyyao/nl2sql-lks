# NL2SQL Agent — Project Summary

## Apa Ini?

NL2SQL Agent adalah aplikasi web berbasis **FastAPI** yang mengubah pertanyaan bahasa natural (Bahasa Indonesia & English) menjadi SQL query, lalu mengeksekusinya pada database SQLite universitas. Sistem ini menggunakan **LLM** (Groq/Anthropic) untuk generate SQL dan **sentence-transformers** untuk intent classification + schema retrieval.

---

## Fitur Utama

| Fitur | Deskripsi |
|-------|-----------|
| **NL2SQL** | Konversi pertanyaan bahasa natural → SQL query secara otomatis |
| **Intent Classification** | Klasifikasi intent user menggunakan cosine similarity (semantic) |
| **Smart Schema Retrieval** | Inject hanya tabel yang relevan ke LLM prompt (hemat token) |
| **Auto-Repair SQL** | Jika SQL gagal eksekusi, otomatis kirim ulang ke LLM untuk diperbaiki |
| **Security Guard** | Cek permission berdasarkan role (admin/user) + demo mode |
| **Query Cache** | Cache hasil SELECT dengan TTL (default 300 detik) |
| **Query Optimizer** | Evaluasi kualitas SQL: score, grade (A-F), suggestions |
| **Visualization** | Auto-generate chart (bar, pie, line, scatter, histogram) dari hasil query |
| **Insight AI** | LLM menganalisis data dan memberikan insight dalam Bahasa Indonesia |
| **Statistics** | Hitung statistik deskriptif (mean, median, std, min, max) |
| **Data Quality** | Cek null values, duplikat, outlier |
| **Report Generation** | Gabungkan tabel + insight + statistik + chart dalam satu laporan HTML |
| **Chat History** | Simpan riwayat percakapan per user di database |
| **Audit Log** | Log semua query yang dijalankan (siapa, kapan, status) |
| **Multi-Model** | Switch antara Llama 3.1/3.3 (Groq) dan Claude Sonnet/Haiku (Anthropic) |
| **Export** | Export hasil query ke CSV, Excel, atau PDF |
| **Auth & RBAC** | Login dengan JWT, role admin vs user |
| **Demo Mode** | Mode presentasi — hanya SELECT yang diizinkan |

---

## Tech Stack

| Layer | Teknologi |
|-------|-----------|
| **Web Framework** | FastAPI + Uvicorn |
| **Frontend** | Jinja2 Templates (HTML/CSS/JS) |
| **Database** | SQLite (data universitas + audit) |
| **LLM Backend** | Groq API (Llama) + Anthropic API (Claude) |
| **LLM Framework** | LangChain (langchain-groq, langchain-anthropic) |
| **Embeddings** | sentence-transformers (`all-MiniLM-L6-v2`) |
| **Visualization** | Matplotlib + Seaborn |
| **Auth** | JWT (python-jose) + Werkzeug password hashing |
| **Data Processing** | Pandas, NumPy |

---

## Database Schema (Universitas)

```
┌──────────────────┐     ┌───────────────────────┐
│     fakultas      │     │  jabatan_fungsional    │
├──────────────────┤     ├───────────────────────┤
│ id_fakultas (PK) │     │ id_jabatan (PK)       │
│ nama_fakultas    │     │ nama_jabatan          │
│ kode_fakultas    │     │ kode_jabatan          │
│ dekan            │     │ angka_kredit_min      │
│ id_dekan (FK)────┼──┐  └───────────┬───────────┘
└──────────────────┘  │              │
                      │              │
              ┌───────┼──────────────┼──────────┐
              │       ▼    dosen     ▼          │
              │  ┌──────────────────────────┐   │
              │  │ id_dosen (PK)            │   │
              │  │ nidn                     │   │
              │  │ nama_lengkap             │   │
              │  │ jenis_kelamin            │   │
              │  │ id_fakultas (FK)─────────┼───┘
              │  │ id_jabatan (FK)──────────┼───┘
              │  │ pendidikan_terakhir      │
              │  │ usia                     │
              │  │ tanggal_bergabung        │
              │  │ status_kepegawaian       │
              │  │ foto                     │
              │  └───────────┬──────────────┘
              │              │
              │              ▼
              │  ┌──────────────────────────┐
              │  │     remunerasi           │
              │  ├──────────────────────────┤
              │  │ id_remunerasi (PK)       │
              │  │ id_dosen (FK)            │
              │  │ tahun                    │
              │  │ bulan                    │
              │  │ gaji_pokok               │
              │  │ tunjangan_jabatan        │
              │  │ tunjangan_fungsional     │
              │  │ tunjangan_kinerja        │
              │  └──────────────────────────┘
              └─────────────────────────────────┘
```

**Relasi FK:**
- `dosen.id_fakultas` → `fakultas.id_fakultas`
- `dosen.id_jabatan` → `jabatan_fungsional.id_jabatan`
- `fakultas.id_dekan` → `dosen.id_dosen`
- `remunerasi.id_dosen` → `dosen.id_dosen`

---

## Cara Menjalankan

```bash
# 1. Clone / download project
cd "LKS AI"

# 2. Buat virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup .env (GROQ_API_KEY wajib)
cp .env.example .env
# Edit .env → isi GROQ_API_KEY dan/atau ANTHROPIC_API_KEY

# 5. Jalankan
uvicorn main:app --reload

# 6. Buka browser
# http://localhost:8000
# Login: admin/admin123 (full access) atau user/user123 (SELECT only)
```

---

## Default Credentials

| Username | Password | Role | Access |
|----------|----------|------|--------|
| `admin` | `admin123` | admin | SELECT, INSERT, UPDATE, DELETE, DROP |
| `user` | `user123` | user | SELECT only |
