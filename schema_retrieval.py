"""
schema_retrieval.py — Semantic Schema Retrieval using Sentence Transformers

Instead of injecting the FULL database schema into every LLM prompt (~900 tokens),
this module embeds table descriptions at startup and retrieves only the top-K
most relevant tables for each user query (~200-300 tokens).

How it works:
    1. Each table gets a rich text description (name + columns + purpose).
    2. At startup, all descriptions are embedded into 384-dim vectors.
    3. At runtime: embed user query → cosine similarity to each table → top-K.
    4. Return formatted schema for ONLY those tables + their FK relationships.

Expected token reduction: ~60-77% (from ~900 to ~200-300 tokens).
"""

from __future__ import annotations

from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer


# ─── Table Descriptions for Embedding ─────────────────────────────────────────
# Each entry: (table_name, description_for_embedding, full_schema_text)
#
# The description is what gets embedded — it should capture the *meaning*
# of the table so cosine similarity works well against user queries.
# The schema_text is what gets injected into the LLM prompt when selected.

TABLE_REGISTRY: list[dict] = [
    {
        "name": "dosen",
        "description": (
            "data dosen, nama lengkap dosen, NIP, NIDN, "
            "pendidikan terakhir, status kepegawaian, "
            "jenis kelamin, usia, tanggal bergabung, foto dosen"
        ),
        "schema": (
            "TABEL: dosen\n"
            "  Kolom: id_dosen (INT (PK)), nidn (varchar(20)), "
            "nama_lengkap (varchar(150)), jenis_kelamin (TEXT), "
            "id_fakultas (INT (FK→fakultas.id_fakultas)), "
            "id_jabatan (INT (FK→jabatan_fungsional.id_jabatan)), "
            "pendidikan_terakhir (TEXT), usia (INT), "
            "tanggal_bergabung (date), status_kepegawaian (TEXT), "
            "foto (varchar(255))\n"
            "  Contoh data: id_dosen=1, nidn='210871520', "
            "nama_lengkap='Bella Mardian Lestari, S.Kom., M.Kom', "
            "jenis_kelamin='P', id_fakultas=4, foto='/foto/juri1.png'\n"
            "  Nilai jenis_kelamin: 'P', 'L'\n"
            "  Nilai pendidikan_terakhir: 'S2', 'S3'\n"
            "  Nilai status_kepegawaian: 'Tetap', 'DPK', 'Kontrak'\n"
            "  Kolom foto: menyimpan path file gambar, format '/foto/<namafile>.<ext>'"
        ),
    },
    {
        "name": "fakultas",
        "description": (
            "fakultas universitas, nama fakultas, kode fakultas, "
            "nama dekan, id dekan, program studi, "
            "dosen di fakultas teknik, FMIPA, hukum, ekonomi"
        ),
        "schema": (
            "TABEL: fakultas\n"
            "  Kolom: id_fakultas (INT (PK)), nama_fakultas (varchar(100)), "
            "kode_fakultas (varchar(10)), dekan (varchar(100)), "
            "id_dekan (INT (FK→dosen.id_dosen))\n"
            "  Contoh data: id_fakultas=1, nama_fakultas='Fakultas Matematika dan IPA', "
            "kode_fakultas='FMIPA', dekan='Prof. Dr. Hendra Kusuma, M.Si', id_dekan=None"
        ),
    },
    {
        "name": "jabatan_fungsional",
        "description": (
            "jabatan akademik dosen, pangkat, nama jabatan fungsional, "
            "angka kredit, tunjangan jabatan fungsional, "
            "lektor, asisten ahli, guru besar, profesor"
        ),
        "schema": (
            "TABEL: jabatan_fungsional\n"
            "  Kolom: id_jabatan (INT (PK)), nama_jabatan (varchar(50)), "
            "kode_jabatan (varchar(10)), angka_kredit_min (INT)\n"
            "  Contoh data: id_jabatan=1, nama_jabatan='Asisten Ahli', "
            "kode_jabatan='AA', angka_kredit_min=150"
        ),
    },
    {
        "name": "remunerasi",
        "description": (
            "gaji dosen, remunerasi, tunjangan kinerja, tunjangan jabatan, "
            "tunjangan fungsional, gaji pokok, periode pembayaran, "
            "total penghasilan, bulan, tahun"
        ),
        "schema": (
            "TABEL: remunerasi\n"
            "  Kolom: id_remunerasi (INT (PK)), "
            "id_dosen (INT (FK→dosen.id_dosen)), tahun (INT), bulan (INT), "
            "gaji_pokok (decimal(12,2)), tunjangan_jabatan (decimal(12,2)), "
            "tunjangan_fungsional (decimal(12,2)), "
            "tunjangan_kinerja (decimal(12,2))\n"
            "  Contoh data: id_remunerasi=1, id_dosen=1, tahun=2025, "
            "bulan=1, gaji_pokok=5931672.7"
        ),
    },
]

# ─── FK Relationship Definitions ─────────────────────────────────────────────
# Maps (source_table, target_table) → relationship description.
# Only included when BOTH tables are in the selected top-K.

FK_RELATIONSHIPS: dict[tuple[str, str], str] = {
    ("dosen", "jabatan_fungsional"): (
        "dosen.id_jabatan → jabatan_fungsional.id_jabatan  "
        "(isi dengan SELECT id_jabatan FROM jabatan_fungsional WHERE nama_jabatan LIKE '%...%')"
    ),
    ("dosen", "fakultas"): (
        "dosen.id_fakultas → fakultas.id_fakultas  "
        "(isi dengan SELECT id_fakultas FROM fakultas WHERE nama_fakultas LIKE '%...%')"
    ),
    ("fakultas", "dosen"): (
        "fakultas.id_dekan → dosen.id_dosen  "
        "(isi dengan SELECT id_dosen FROM dosen WHERE nama_lengkap LIKE '%...%')"
    ),
    ("remunerasi", "dosen"): (
        "remunerasi.id_dosen → dosen.id_dosen  "
        "(isi dengan SELECT id_dosen FROM dosen WHERE nama_lengkap LIKE '%...%')"
    ),
}

# ─── FK Insert Rules (always appended when any FK table is selected) ─────────
FK_INSERT_RULES = """\
ATURAN INSERT FK:
  - Kolom PK (id_dosen, id_fakultas, id_jabatan, id_remunerasi): gunakan (SELECT COALESCE(MAX(id_xxx), 0) + 1 FROM tabel)
  - Kolom FK (id_dekan, id_fakultas di dosen, id_jabatan di dosen, id_dosen di remunerasi):
    JANGAN MAX+1! Gunakan SELECT untuk mencari ID yang sudah ada di tabel relasi berdasarkan nama."""


class SchemaRetriever:
    """
    Semantic schema retriever using sentence-transformer embeddings.

    At init:  embeds table descriptions into vectors.
    At runtime: embed query → cosine similarity → top-K tables → formatted schema.

    Example:
        >>> retriever = SchemaRetriever()
        >>> retriever.get_relevant_table_names("total gaji dosen", top_k=2)
        ['remunerasi', 'dosen']
        >>> schema = retriever.get_relevant_schema("total gaji dosen", top_k=2)
        # Returns formatted schema with only remunerasi + dosen tables
    """

    def __init__(
        self,
        model: SentenceTransformer | None = None,
        model_name: str = "all-MiniLM-L6-v2",
    ) -> None:
        # Share model with IntentClassifier to avoid loading twice
        self.model: SentenceTransformer = model or SentenceTransformer(model_name)

        # Build parallel arrays
        self._table_names: list[str] = []
        self._descriptions: list[str] = []
        self._schemas: list[str] = []

        for entry in TABLE_REGISTRY:
            self._table_names.append(entry["name"])
            self._descriptions.append(entry["description"])
            self._schemas.append(entry["schema"])

        # Pre-embed all table descriptions → shape (num_tables, 384)
        self._embeddings: np.ndarray = self.model.encode(
            self._descriptions,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)

    def get_relevant_table_names(
        self, query: str, top_k: int = 2
    ) -> List[str]:
        """
        Return the names of the top-K most relevant tables for a query.

        Args:
            query: The user's natural-language question.
            top_k: Number of tables to return (capped at total tables).

        Returns:
            List of table names, ordered by relevance (highest first).
        """
        top_k = min(top_k, len(self._table_names))

        query_vec: np.ndarray = self.model.encode(
            query, normalize_embeddings=True, show_progress_bar=False
        ).astype(np.float32)

        # Cosine similarity (dot product on normalized vectors)
        similarities: np.ndarray = self._embeddings @ query_vec

        # Top-K indices (descending)
        top_indices = np.argsort(similarities)[::-1][:top_k]

        return [self._table_names[i] for i in top_indices]

    def get_relevant_schema(
        self, query: str, top_k: int = 2
    ) -> str:
        """
        Return a formatted schema string containing ONLY the top-K
        most relevant tables + their FK relationships.

        Args:
            query: The user's natural-language question.
            top_k: Number of tables to include.

        Returns:
            Formatted schema string ready for LLM prompt injection.
        """
        top_k = min(top_k, len(self._table_names))

        query_vec = self.model.encode(
            query, normalize_embeddings=True, show_progress_bar=False
        ).astype(np.float32)
        similarities = self._embeddings @ query_vec
        top_indices = np.argsort(similarities)[::-1][:top_k]

        selected_names = set(self._table_names[i] for i in top_indices)

        # ── Build schema sections ─────────────────────────────────────────
        parts: list[str] = ["=== STRUKTUR DATABASE UNIVERSITAS ===\n"]

        for idx in top_indices:
            parts.append(self._schemas[idx])
            parts.append("")  # blank line separator

        # ── Add relevant FK relationships ─────────────────────────────────
        fk_lines: list[str] = []
        for (src, tgt), desc in FK_RELATIONSHIPS.items():
            if src in selected_names or tgt in selected_names:
                fk_lines.append(f"  {desc}")

        if fk_lines:
            parts.append("────────────────────────────────────────────────────────────")
            parts.append("RELASI ANTAR TABEL (FK):")
            parts.extend(fk_lines)
            parts.append("")
            parts.append(FK_INSERT_RULES)

        return "\n".join(parts)

    def get_similarities(self, query: str) -> dict[str, float]:
        """
        Debug helper: return cosine similarity scores for all tables.
        """
        query_vec = self.model.encode(
            query, normalize_embeddings=True, show_progress_bar=False
        ).astype(np.float32)
        similarities = self._embeddings @ query_vec
        return {
            name: round(float(sim), 4)
            for name, sim in zip(self._table_names, similarities)
        }


# ─── Module-Level Singleton ───────────────────────────────────────────────────
# Shares the same sentence-transformer model with IntentClassifier
# to avoid loading the model twice (~80MB).

def _create_retriever() -> SchemaRetriever:
    """Create SchemaRetriever, sharing model with IntentClassifier if available."""
    try:
        from intent_classifier import intent_classifier
        shared_model = intent_classifier.model
        print("[SchemaRetriever] Sharing model with IntentClassifier.")
    except ImportError:
        shared_model = None
        print("[SchemaRetriever] Loading own sentence-transformer model...")

    return SchemaRetriever(model=shared_model)


print("[SchemaRetriever] Initializing...")
schema_retriever = _create_retriever()
print(f"[SchemaRetriever] Ready. {len(schema_retriever._table_names)} tables embedded.")
