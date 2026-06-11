import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config

ALGORITHM    = "HS256"
TOKEN_EXPIRE = timedelta(hours=8)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def setup_user_database():
    conn = sqlite3.connect(Config.AUDIT_DB_PATH)
    conn.execute("""
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
    conn.commit()

    for username, info in Config.USERS.items():
        exists = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO users (username, password_hash, name, role) VALUES (?,?,?,?)",
                (username, generate_password_hash(info["password"]),
                 info["name"], info["role"])
            )
            print(f"[AUTH] User '{username}' ({info['role']}) dibuat.")

    conn.commit()
    conn.close()


def create_access_token(username: str, role: str, name: str) -> str:
    payload = {
        "sub":  username,
        "role": role,
        "name": name,
        "exp":  datetime.utcnow() + TOKEN_EXPIRE,
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, Config.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def verify_credentials(username: str, password: str) -> Optional[dict]:
    try:
        conn = sqlite3.connect(Config.AUDIT_DB_PATH)
        row  = conn.execute(
            "SELECT username, password_hash, name, role FROM users "
            "WHERE username = ? AND active = 1", (username,)
        ).fetchone()
        conn.close()
        if row and check_password_hash(row[1], password):
            return {"username": row[0], "name": row[2], "role": row[3]}
        return None
    except Exception:
        return None


def get_all_users() -> list:
    try:
        conn = sqlite3.connect(Config.AUDIT_DB_PATH)
        rows = conn.execute(
            "SELECT id, username, name, role, active, created_at "
            "FROM users ORDER BY role, username"
        ).fetchall()
        conn.close()
        return [
            {"id": r[0], "username": r[1], "name": r[2],
             "role": r[3], "active": bool(r[4]), "created_at": r[5]}
            for r in rows
        ]
    except Exception:
        return []


def add_user(username: str, password: str, name: str, role: str) -> dict:
    if role not in ("admin", "user"):
        return {"success": False, "error": "Role harus 'admin' atau 'user'."}
    try:
        conn = sqlite3.connect(Config.AUDIT_DB_PATH)
        conn.execute(
            "INSERT INTO users (username, password_hash, name, role) VALUES (?,?,?,?)",
            (username, generate_password_hash(password), name, role)
        )
        conn.commit()
        conn.close()
        return {"success": True}
    except sqlite3.IntegrityError:
        return {"success": False, "error": f"Username '{username}' sudah digunakan."}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_current_user(
    request: Request,
    bearer_token: Optional[str] = Depends(oauth2_scheme),
) -> dict:

    token = bearer_token

    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi tidak valid. Silakan login ulang.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired atau tidak valid. Silakan login ulang.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "username": payload["sub"],
        "role":     payload["role"],
        "name":     payload["name"],
    }


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak. Hanya admin yang bisa mengakses ini.",
        )
    return user


async def get_user_from_cookie(request: Request) -> Optional[dict]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    payload = decode_token(token)
    if not payload:
        return None
    return {
        "username": payload["sub"],
        "role":     payload["role"],
        "name":     payload["name"],
    }
