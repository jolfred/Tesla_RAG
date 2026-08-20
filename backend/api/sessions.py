import hashlib
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.config import SESSION_TTL, SESSIONS_DB
from backend.utils.logger import setup_logger

logger = setup_logger("sessions")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    """SHA-256 хэш opaque-токена (в БД хранится только хэш, NFR-3)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionStore:
    """SQLite-хранилище сессий.

    Хранит только SHA-256 хэш токена, роль, vk_user_id и сроки.
    Проверка сессии — единичный PK-поиск (NFR-1, миллисекунды).
    Перезапуск сервера не сбрасывает сессии (файл БД, NFR-2).
    """

    def __init__(self, db_path: Optional[str] = None, ttl_days: Optional[int] = None):
        self.db_path = str(db_path or SESSIONS_DB)
        self.ttl_days = ttl_days if ttl_days is not None else SESSION_TTL
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()
        self.cleanup()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    role TEXT NOT NULL,
                    vk_user_id TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)"
            )
            self._conn.commit()

    def create(self, role: str = "user", vk_user_id: Optional[str] = None) -> dict:
        """Создаёт сессию, возвращает {token, role, vk_user_id, expires_at}."""
        token = secrets.token_urlsafe(32)
        now = _utcnow()
        expires = now + timedelta(days=self.ttl_days)
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (token_hash, role, vk_user_id, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    hash_token(token),
                    role,
                    vk_user_id,
                    now.isoformat(),
                    expires.isoformat(),
                ),
            )
            self._conn.commit()
        return {
            "token": token,
            "role": role,
            "vk_user_id": vk_user_id,
            "expires_at": expires.isoformat(),
        }

    def verify(self, token: str) -> Optional[dict]:
        """Проверка токена: хэш -> PK-поиск -> срок. Возвращает сессию или None."""
        if not token:
            return None
        token_hash = hash_token(token)
        with self._lock:
            row = self._conn.execute(
                "SELECT role, vk_user_id, expires_at FROM sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            if row is None:
                return None
            session = {
                "role": row["role"],
                "vk_user_id": row["vk_user_id"],
                "expires_at": row["expires_at"],
            }
            expires = datetime.fromisoformat(session["expires_at"])
            if expires <= _utcnow():
                self._conn.execute(
                    "DELETE FROM sessions WHERE token_hash = ?", (token_hash,)
                )
                self._conn.commit()
                return None
        return session

    def revoke(self, token: str) -> bool:
        """Отзыв токена: удаление записи из БД (FR-1.4)."""
        if not token:
            return False
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM sessions WHERE token_hash = ?", (hash_token(token),)
            )
            self._conn.commit()
            return cur.rowcount > 0

    def cleanup(self) -> int:
        """Ленивая очистка истёкших сессий (FR-1.5)."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM sessions WHERE expires_at <= ?", (_utcnow().isoformat(),)
            )
            self._conn.commit()
            return cur.rowcount

    def clear(self) -> int:
        """Полная очистка таблицы (используется в тестах)."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM sessions")
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()


store = SessionStore()