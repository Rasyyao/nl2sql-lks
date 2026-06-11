import sqlite3
import os
from config import Config
import random
from datetime import date, timedelta, datetime

def setup_audit_database():

    conn = sqlite3.connect(Config.AUDIT_DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT NOT NULL,
            role        TEXT NOT NULL,
            pertanyaan  TEXT,
            sql_query   TEXT,
            waktu       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status      TEXT CHECK(status IN ('allowed', 'blocked', 'executed', 'error')),
            pesan       TEXT
        )
    """)

    
    c.execute("""
        CREATE TABLE IF NOT EXISTS query_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            question   TEXT NOT NULL,
            sql_query  TEXT NOT NULL,
            rowcount   INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    
    c.execute("""
        CREATE TABLE IF NOT EXISTS metrics_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            sql_gen_ms REAL,
            exec_ms    REAL,
            success    INTEGER,
            blocked    INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name          TEXT NOT NULL,
            role          TEXT NOT NULL CHECK(role IN ('admin', 'user')),
            active        INTEGER DEFAULT 1,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT NOT NULL,
            role        TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
            content     TEXT NOT NULL,
            sql_query   TEXT,
            table_data  TEXT,
            visualization TEXT,
            metadata    TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (username) REFERENCES users(username)
        )
    """)

    conn.commit()
    conn.close()
    print(f"[AUDIT] Database audit/auth siap: {Config.AUDIT_DB_PATH}")


def init_all():
    """Inisialisasi semua database saat aplikasi start."""
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
    setup_audit_database()


if __name__ == "__main__":
    init_all()
