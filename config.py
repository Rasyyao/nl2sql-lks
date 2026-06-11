# config.py — Konfigurasi terpusat dari .env
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # App
    SECRET_KEY   = os.getenv("SECRET_KEY", "")
    DEBUG        = os.getenv("DEBUG", "True").lower() == "true"

    # Groq API
    GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL      = os.getenv("GROQ_MODEL", "")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0))

    # Anthropic / Claude API
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

    DATABASE_PATH = os.getenv("DATABASE_PATH", "universitas_lks_2026-04-12.db")
    AUDIT_DB_PATH = os.getenv("AUDIT_DB_PATH", "audit.db")

    UPLOAD_FOLDER      = os.getenv("UPLOAD_FOLDER", "uploads")
    ALLOWED_EXTENSIONS = {"db", "csv"}
    MAX_UPLOAD_MB      = 16

    DANGEROUS_OPERATIONS = ["DELETE", "DROP", "UPDATE", "INSERT", "TRUNCATE", "ALTER"]

    USERS = {
        "admin": {"password": "admin123", "role": "admin", "name": "Administrator"},
        "user":  {"password": "user123",  "role": "user",  "name": "Pengguna"},
    }

    QUERY_CACHE_TTL = int(os.getenv("QUERY_CACHE_TTL", "300"))

    DEMO_MODE_DEFAULT = os.getenv("DEMO_MODE", "false").lower() == "true"

    AVAILABLE_MODELS = {
        # Groq models
        "llama-3.1-8b-instant": {
            "label":    "Llama 3.1 8B Instant",
            "provider": "groq",
            "desc":     "Cepat & ringan — cocok untuk query sederhana",
            "badge":    "⚡ Groq",
            "color":    "amber",
            "speed":    "Sangat Cepat",
        },
        "llama-3.3-70b-versatile": {
            "label":    "Llama 3.3 70B Versatile",
            "provider": "groq",
            "desc":     "Akurasi tinggi — cocok untuk query kompleks",
            "badge":    "🦙 Groq",
            "color":    "orange",
            "speed":    "Cepat",
        },
        # Anthropic / Claude models
        "claude-sonnet-4-6": {
            "label":    "Claude Sonnet 4.6",
            "provider": "anthropic",
            "desc":     "Cerdas & seimbang — SQL kompleks & penjelasan detail",
            "badge":    "✦ Claude",
            "color":    "brand",
            "speed":    "Sedang",
        },
        "claude-haiku-4-5-20251001": {
            "label":    "Claude Haiku 4.5",
            "provider": "anthropic",
            "desc":     "Efisien & hemat — cocok untuk query sehari-hari",
            "badge":    "✦ Claude",
            "color":    "emerald",
            "speed":    "Cepat",
        },
    }

    # DEFAULT_MODEL = "llama-3.1-8b-instant"
    DEFAULT_MODEL = "claude-haiku-4-5-20251001"
