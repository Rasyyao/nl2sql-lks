"""
intent_classifier.py — Semantic Intent Classification using Sentence Transformers

Replaces the old TF-IDF keyword-based classifier with cosine similarity
against pre-embedded intent prototypes. Each intent has multiple example
sentences in Bahasa Indonesia + English; at runtime the user query is
embedded and compared to all prototypes to find the best match.

Cosine Similarity:
    cos(A, B) = (A · B) / (‖A‖ × ‖B‖)
    Measures directional similarity between two vectors (0 = orthogonal,
    1 = identical direction). Sentence-transformers already L2-normalize
    embeddings, so dot product equals cosine similarity.
"""

from __future__ import annotations

import numpy as np
from sentence_transformers import SentenceTransformer

# ─── Intent Prototype Definitions ─────────────────────────────────────────────
# Each intent maps to a list of representative example sentences.
# The classifier picks the intent whose prototype is closest to the user query.

INTENT_PROTOTYPES: dict[str, list[str]] = {
    # ── SELECT: any database data query ───────────────────────────────────
    "SELECT": [
        # Bahasa Indonesia
        "tampilkan semua dosen",
        "berikan daftar fakultas",
        "siapa dosen di fakultas teknik",
        "lihat data remunerasi",
        "cari dosen bernama Bella",
        "jumlah dosen aktif",
        "total gaji pokok semua dosen",
        "rata-rata tunjangan kinerja",
        "berapa banyak fakultas yang ada",
        "daftar jabatan fungsional",
        "dosen dengan gaji tertinggi",
        "siapa saja dosen yang berstatus kontrak",
        "tampilkan nama dan NIP dosen",
        "data dosen fakultas MIPA",
        "berikan informasi remunerasi periode 2025",
        "perbandingan gaji antar fakultas",
        "statistik dosen berdasarkan pendidikan",
        "grafik tunjangan kinerja dosen",
        "laporan data dosen lengkap",
        "buatkan laporan remunerasi",
        "visualisasi jumlah dosen per fakultas",
        # English
        "show me all data",
        "list all lecturers",
        "how many professors are there",
        "get salary information",
        "find faculty with most lecturers",
        "display remuneration details",
        "who has the highest salary",
        "show lecturer data from engineering faculty",
    ],

    # ── GREETING: casual greetings ────────────────────────────────────────
    "GREETING": [
        "halo",
        "hai",
        "hello",
        "hi",
        "hei",
        "selamat pagi",
        "selamat siang",
        "selamat sore",
        "selamat malam",
        "assalamualaikum",
        "hey there",
        "good morning",
        "apa kabar",
    ],

    # ── OUT_OF_SCOPE: questions unrelated to the university database ──────
    "OUT_OF_SCOPE": [
        "siapa presiden indonesia",
        "buatkan kue",
        "what is the weather",
        "berapa harga bitcoin",
        "cara memasak nasi goreng",
        "siapa pemenang piala dunia",
        "apa itu machine learning",
        "translate this to english",
        "tulis puisi tentang cinta",
        "how to learn python",
        "berita terbaru hari ini",
        "rekomendasi film bagus",
    ],

    # ── CLARIFICATION: user is confused or asking for explanation ──────────
    "CLARIFICATION": [
        "maksudnya apa",
        "bisa dijelaskan",
        "what do you mean",
        "saya tidak mengerti",
        "tolong jelaskan lagi",
        "bisa ulangi",
        "apa maksud pertanyaan ini",
        "kurang jelas",
        "can you explain",
        "I don't understand",
        "jelaskan lebih detail",
    ],

    # ── SCHEMA_QUESTION: asking about database structure ──────────────────
    "SCHEMA_QUESTION": [
        "tabel apa saja yang ada",
        "kolom apa saja di tabel dosen",
        "struktur database",
        "ada tabel apa di database ini",
        "schema database",
        "skema tabel",
        "relasi antar tabel",
        "what tables are available",
        "show database schema",
        "daftar kolom tabel remunerasi",
    ],

    # ── EDUKASI_QUESTION: asking about how the system works ───────────────
    "EDUKASI_QUESTION": [
        "apa itu nl2sql",
        "cara kerja agent ini",
        "bagaimana sistem ini bekerja",
        "apa itu sql agent",
        "jelaskan cara kerja NL2SQL",
        "how does this system work",
        "apa teknologi di balik ini",
        "bagaimana query dihasilkan",
    ],
}

# ── Confidence threshold ─────────────────────────────────────────────────────
# If the best prototype score is below this, fall back to OUT_OF_SCOPE.
DEFAULT_THRESHOLD: float = 0.40


class IntentClassifier:
    """
    Semantic intent classifier using sentence-transformer embeddings.

    At init:  loads model + pre-embeds all intent prototypes.
    At runtime: embeds user query → cosine similarity → best intent.

    Example:
        >>> classifier = IntentClassifier()
        >>> classifier.classify("berikan daftar dosen")
        {"intent": "SELECT", "confidence": 0.87}
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        threshold: float = DEFAULT_THRESHOLD,
        model: SentenceTransformer | None = None,
    ) -> None:
        # Allow sharing a pre-loaded model (e.g. with SchemaRetriever)
        self.model: SentenceTransformer = model or SentenceTransformer(model_name)
        self.threshold = threshold

        # Flatten prototypes into parallel lists for batch embedding
        self._sentences: list[str] = []
        self._labels: list[str] = []
        for intent, examples in INTENT_PROTOTYPES.items():
            for ex in examples:
                self._sentences.append(ex)
                self._labels.append(intent)

        # Pre-embed all prototypes → shape (N, 384)
        # Embeddings are L2-normalized by default, so dot product = cosine sim.
        # Explicit float32 cast prevents overflow warnings with some model versions.
        self._embeddings: np.ndarray = self.model.encode(
            self._sentences,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)

    def classify(self, query: str, threshold: float | None = None) -> dict:
        """
        Classify a user query into one of the defined intents.

        Args:
            query:     The user's natural-language question.
            threshold: Override the default confidence threshold.

        Returns:
            dict with keys:
                - "intent" (str):     The classified intent name.
                - "confidence" (float): Cosine similarity score [0, 1].
        """
        th = threshold if threshold is not None else self.threshold

        # Embed the query → shape (384,)
        query_vec: np.ndarray = self.model.encode(
            query,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).astype(np.float32)

        # Cosine similarity = dot product (vectors are already normalized)
        # np.errstate suppresses harmless warnings from model warmup on first call
        with np.errstate(divide='ignore', over='ignore', invalid='ignore'):
            similarities: np.ndarray = self._embeddings @ query_vec  # shape (N,)

        best_idx: int = int(np.argmax(similarities))
        best_score: float = float(similarities[best_idx])

        if best_score < th:
            return {"intent": "OUT_OF_SCOPE", "confidence": round(best_score, 4)}

        return {
            "intent": self._labels[best_idx],
            "confidence": round(best_score, 4),
        }

    def classify_top_k(self, query: str, k: int = 3) -> list[dict]:
        """
        Return the top-K intent matches with their confidence scores.
        Useful for debugging and threshold tuning.
        """
        query_vec = self.model.encode(
            query, normalize_embeddings=True, show_progress_bar=False
        ).astype(np.float32)
        similarities = self._embeddings @ query_vec

        # Get top-K indices
        top_indices = np.argsort(similarities)[::-1][:k]

        results = []
        for idx in top_indices:
            results.append({
                "intent": self._labels[idx],
                "matched_prototype": self._sentences[idx],
                "confidence": round(float(similarities[idx]), 4),
            })
        return results


# ─── Module-Level Singleton ───────────────────────────────────────────────────
# Loaded ONCE at import time; reused across all requests.
# The model instance is exposed so SchemaRetriever can share it.

print("[IntentClassifier] Loading sentence-transformer model...")
intent_classifier = IntentClassifier()
print("[IntentClassifier] Ready. "
      f"{len(intent_classifier._sentences)} prototypes embedded.")
