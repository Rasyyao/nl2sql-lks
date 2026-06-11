# NL2SQL Agent — Build From Scratch Guide

Panduan step-by-step dan daftar modul, fungsi, serta class yang harus dibuat untuk membangun NL2SQL Agent dari awal.

---

## 🛠️ Step 1: Project Setup

### 1.1 Buat Folder Struktur
```bash
mkdir nl2sql-agent
cd nl2sql-agent
mkdir static templates foto uploads docs
```

### 1.2 Virtual Environment & Install Dependencies
```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
# atau: venv\Scripts\activate  # Windows

pip install fastapi uvicorn[standard] python-multipart jinja2 aiofiles
pip install langchain langchain-groq langchain-core
pip install python-jose[cryptography] werkzeug python-dotenv
pip install sentence-transformers numpy pandas openpyxl matplotlib seaborn
```

### 1.3 Buat File Konfigurasi `.env`
Siapkan environment variables untuk menyimpan API keys, path database, model default, dan environment mode.

---

## 🏗️ Step 2: Daftar Modul & Fungsi (Build Order)

Ikuti urutan build di bawah ini untuk menghindari error dependency.

### 1. `config.py` — Sentralisasi Konfigurasi
Modul untuk membaca dan mengelola semua environment variables dari file `.env`.
* **Class `Config`**: Menyimpan attribute konfigurasi (API keys, DB path, model list, security rule, user static, dan configuration defaults).

### 2. `database_setup.py` — Database Inisialisasi
Bertanggung jawab membuat database audit dan history chat saat pertama kali dijalankan.
* `setup_audit_database()`: Membuat tabel `audit_log`, `chat_history`, dan `metrics_log` di SQLite (`audit.db`).
* `init_all()`: Membuat direktori output yang dibutuhkan (`uploads/`, `foto/`) dan memanggil fungsi inisialisasi tabel.

### 3. `auth.py` — Authentication & User Management
Mengatur autentikasi berbasis JWT Token dan otorisasi role user.
* `setup_user_database()`: Membuat tabel `users` di `audit.db` dan menyematkan akun default (`admin` dan `user`) dengan hashed password.
* `create_access_token(username, role, name)`: Membuat JWT Token dengan masa aktif 8 jam yang di-encode dengan `SECRET_KEY`.
* `verify_credentials(username, password)`: Memverifikasi kesesuaian username dan password terhadap hashed password di database.
* `get_current_user(request)`: FastAPI dependency untuk mengekstrak dan memverifikasi JWT token dari cookie atau authorization header.
* `require_admin(user)`: Middleware dependency untuk memastikan user yang login memiliki role `admin`.
* `get_user_from_cookie(request)`: Mengambil data payload user langsung dari cookie request.
* `get_all_users()`: Mengambil list seluruh user terdaftar.
* `add_user(username, password, name, role)`: Menambahkan user baru ke database dengan password terenkripsi.

### 4. `intent_classifier.py` — Semantic Intent Classification
Mengklasifikasikan intent pertanyaan pengguna menggunakan cosine similarity dari sentence-transformers.
* **Class `IntentClassifier`**
  * `__init__(model_name, threshold, model)`: Memuat model sentence transformer dan melakukan pre-embedding pada seluruh prototype intent query saat startup agar proses klasifikasi cepat.
  * `classify(query)`: Mengubah query user menjadi embedding vector, menghitung cosine similarity (dot product) terhadap embedding prototype, dan mengembalikan intent terbaik di atas threshold.
  * `classify_top_k(query, k)`: Mengembalikan daftar top-K intent yang paling mendekati beserta skor kecocokannya.

### 5. `schema_retrieval.py` — Semantic Schema Retrieval
Memilih dan mengembalikan schema tabel yang relevan secara dinamis untuk dikirim ke LLM (menggantikan injeksi seluruh schema database).
* **Class `SchemaRetriever`**
  * `__init__(model, model_name)`: Menggunakan embedding model yang sama dengan IntentClassifier dan melakukan pre-embedding pada deskripsi tabel database (nama tabel, kolom, relasi key).
  * `get_relevant_table_names(query, top_k)`: Mengambil daftar nama tabel terbaik yang paling relevan dengan query.
  * `get_relevant_schema(query, top_k)`: Menggabungkan dan mengembalikan string deskripsi schema dari tabel-tabel relevan terpilih untuk disuntikkan ke prompt LLM.
  * `get_similarities(query)`: Fungsi debugging untuk melihat skor kesamaan query dengan masing-masing tabel.

### 6. `guards.py` — SQL Security Guard
Mengamankan database dari operasi berbahaya dan membatasi hak akses role.
* `check_sql_permission(sql, role)`: Memeriksa apakah statement SQL yang dihasilkan diizinkan untuk role terkait (user: SELECT-only, admin: write dengan konfirmasi).
* `validate_sql_syntax(sql)`: Memastikan query SQL memiliki keyword pembuka yang valid dan mencegah eksekusi multi-statement (SQL Injection block).
* `set_demo_mode(enabled)`: Mengubah status demo mode secara dinamis.
* `is_demo_mode()`: Mengecek status keaktifan demo mode (saat aktif, semua query dipaksa read-only).

### 7. `query_cache.py` — Query Result Cache
Menyimpan hasil query SELECT secara sementara untuk mempercepat respons sistem.
* `get_cached_result(sql)`: Mengambil hasil query dari memori cache menggunakan MD5 hash dari string SQL sebagai key.
* `set_cached_result(sql, result)`: Menyimpan hasil query SELECT yang berhasil dijalankan ke dalam cache dengan validitas waktu (TTL).
* `invalidate_cache()`: Menghapus seluruh data cache (dijalankan otomatis setelah ada query modifikasi data / INSERT/UPDATE/DELETE).
* `get_cache_stats()`: Memberikan informasi jumlah hit dan miss cache untuk analytics.

### 8. `utils.py` — Database & File Utilities
Menampung seluruh helper database, logging audit, ekspor file, dan pengelolaan chat history.
* `load_schema_to_cache(db_path)`: Membaca metadata schema database SQLite ke cache memori lokal.
* `execute_sql(sql, db_path)`: Menjalankan query SQL ke database SQLite dan mengembalikan data (headers & rows) atau rowcount.
* `run_explain_query(sql, db_path)`: Menjalankan perintah EXPLAIN QUERY PLAN untuk melihat performa query.
* `log_to_audit(username, role, pertanyaan, sql_query, status, pesan)`: Menyimpan jejak aktivitas query ke tabel `audit_log`.
* `get_audit_logs(limit)`: Mengambil data log audit terbaru.
* `export_to_csv(columns, rows)`: Memformat data tabel hasil query menjadi format CSV string.
* `export_to_excel(columns, rows)`: Mengonversi data tabel menjadi bytes file Excel (.xlsx).
* `save_chat_message(...)`: Menyimpan pesan percakapan, query SQL, data tabel, dan status visualisasi ke tabel `chat_history`.
* `get_chat_history(username, limit)`: Mengambil percakapan sebelumnya untuk ditampilkan pada UI chat.
* `clear_chat_history(username)`: Menghapus riwayat percakapan user dari database.

### 9. `agent.py` — NL2SQL Core Agent
Orchestrator utama yang menghubungkan LLM dengan intent, schema retrieval, pembersihan SQL, serta penerjemahan jawaban.
* `get_llm(temperature)`: Menginisialisasi interface model LLM (Groq Llama atau Anthropic Claude) sesuai model aktif.
* `classify_intent(question)`: Menghubungkan query ke Intent Classifier untuk diterjemahkan menjadi pipeline status.
* `handle_non_sql(intent)`: Menghasilkan pesan teks langsung untuk intent non-SQL (seperti salam, pertanyaan seputar schema, atau di luar cakupan).
* `build_prompt(question, schema, history_ctx)`: Merakit system instruction, schema database, konteks chat history, dan pertanyaan user menjadi satu prompt LLM yang komprehensif.
* `generate_sql(question, chat_history)`: Alur utama konversi text-to-SQL (Klasifikasi -> Ambil Schema -> LLM invoke -> Bersihkan output).
* `auto_repair_sql(question, broken_sql, error)`: Mengirimkan error eksekusi SQL kembali ke LLM untuk diperbaiki secara otomatis.
* `clean_sql_output(raw)`: Membersihkan markdown block, backticks, komentar, atau karakter spasi liar dari hasil query LLM.
* `generate_natural_answer(question, sql, result)`: Menerjemahkan data hasil query database menjadi kalimat jawaban natural menggunakan LLM.
* `generate_insight(question, columns, rows)`: Menganalisis data hasil query untuk memberikan 3-4 poin insight tambahan.
* `calculate_statistics(columns, rows)`: Melakukan analisis deskriptif statistik sederhana (mean, median, std, min, max) dari kolom angka.
* `check_data_quality(columns, rows)`: Memeriksa kualitas data (ada/tidaknya null values, duplikat data, atau outlier).
* `explain_sql_error_friendly(question, sql, error)`: Menerjemahkan error teknis SQL menjadi penjelasan sederhana yang ramah pengguna.
* `set_active_model(model_id)`: Mengubah model LLM aktif yang digunakan oleh agent.
* `_inject_auto_id(sql)`: Otomatis mendeteksi statement INSERT untuk menyisipkan ID baru (MAX + 1) jika PK tidak disertakan.
* `_preprocess_foto_update(question)`: Mengekstrak metadata nama dosen dan foto untuk proses upload profil.

### 10. `query_optimizer.py` — SQL Quality Evaluator
Mengevaluasi kualitas query SQL yang dihasilkan oleh agent berdasarkan aturan anti-pattern database.
* `evaluate_sql(sql, question)`: Memeriksa query SQL terhadap 13 aturan optimasi (misalnya: SELECT *, implicit join, wildcard di awal LIKE) dan mengembalikan skor (0-100), grade (A-F), serta rekomendasi perbaikan.

### 11. `visualizer.py` — Chart Generator
Menganalisis data hasil query dan merender grafik visualisasi yang sesuai secara otomatis.
* `detect_viz_intent(question)`: Mendeteksi apakah user meminta visualisasi grafik dalam pertanyaannya.
* `suggest_chart_type(columns, rows, question)`: Memilih tipe grafik terbaik (bar, line, scatter, pie) berdasarkan bentuk dan tipe data hasil query.
* `generate_chart(columns, rows, question)`: Membuat grafik menggunakan Matplotlib/Seaborn dan menyimpannya sebagai base64 encoded PNG.

### 12. `observability.py` — Metrics & Request Timer
Mengukur performa sistem dan mencatat latensi.
* **Class `Timer`**: Context manager untuk mencatat waktu eksekusi proses dalam satuan milidetik.
* `record_request(sql_gen_ms, exec_ms, success, blocked)`: Menyimpan metrik durasi pemrosesan dan status request ke `metrics_log`.
* `get_metrics()`: Mengagregasikan seluruh data performa (rata-rata latensi, success rate, block rate) untuk dashboard.

### 13. `main.py` — FastAPI Web Server
Titik masuk aplikasi (entry point) yang melayani HTTP request, menyajikan file statis, dan mengorkestrasi pipeline backend.
* `startup()`: Fungsi startup FastAPI untuk inisialisasi folder, database audit, cache schema, dan seating default users.
* `api_ask(body, user)`: Endpoint utama `POST /api/ask` untuk memproses pertanyaan user, memicu pipeline, menyimpan riwayat percakapan, dan mencatat audit log.
* `_run_pipeline(sql, question, user)`: Menjalankan sub-pipeline eksekusi SQL: Cek syntax -> Cek guard -> Cek cache -> Jalankan explain query -> Eksekusi DB -> Auto-repair jika error -> Render answer & chart -> Log hasil.
* `_error_response(message, status)`: Helper untuk membuat respons error terstandarisasi.
* `_check_name_mismatch(question, rows)`: Memeriksa apakah LLM memfilter nama dosen yang typo atau tidak ada di database.
* `_suggest_similar_names(wrong_name)`: Memberikan saran nama dosen terdekat jika pencarian tidak menemukan kecocokan exact.

---

## 🎨 Step 3: Frontend Templates (`templates/`)

Buat halaman antarmuka web menggunakan Jinja2 HTML + CSS/JS vanila di folder `templates/`:
1. `login.html`: Halaman masuk menggunakan JWT Auth.
2. `chat.html`: Halaman chat interaktif untuk mengirim pertanyaan, melihat respons teks, tabel data, visualisasi chart, visualisasi query optimizer, dan tombol ekspor.
3. `admin_dashboard.html`: Halaman pemantauan log audit, metrik latensi grafis, toggle demo mode, dan form pendaftaran user baru.
4. `panduan.html`: Halaman dokumentasi interaktif edukasi sistem.

---

## 🚀 Step 4: Run & Test

Jalankan server pengembangan:
```bash
uvicorn main:app --reload --port 8002
```

Lakukan pengujian fungsionalitas berikut:
1. **Chatting**: Masukkan "tampilkan dosen" dan verifikasi hasil berupa tabel dan teks jawaban natural.
2. **Intent & Schema Routing**: Ajukan pertanyaan non-SQL seperti "halo" atau pertanyaan di luar konteks, pastikan dijawab sesuai intent.
3. **Security Guard**: Login sebagai `user` (non-admin), coba lakukan query UPDATE/DELETE, pastikan operasi diblokir.
4. **Admin Dashboard**: Akses `/admin` dan verifikasi log audit serta metrik request tercatat dengan benar.
