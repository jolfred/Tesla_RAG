"""Секреты без рестарта: приоритет admin.db -> os.getenv.

Клиенты читают ключи через get_secret() при каждом обращении (с коротким
TTL-кэшем), поэтому обновление ключа в админке подхватывается следующим
job/запросом без перезапуска API. Значения наружу никогда не отдаём —
только флаги is_set (см. роутер admin).
"""

from __future__ import annotations

import os
import time

from backend.admin.db import ADMIN_DB, get_connection

_TTL = 30.0
_cache: dict[str, tuple[float, str]] = {}


def _db_value(key: str) -> str:
    if not ADMIN_DB.exists():
        return ""
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return str(row["value"]) if row else ""
        finally:
            conn.close()
    except Exception:
        return ""


def get_secret(key: str, default: str = "") -> str:
    """Значение секрета: override из admin.db, иначе окружение."""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and now - hit[0] < _TTL:
        if hit[1]:
            return hit[1]
    else:
        db_val = _db_value(key)
        _cache[key] = (now, db_val)
        if db_val:
            return db_val
    return os.getenv(key, default)


def drop_cache(key: str | None = None) -> None:
    if key is None:
        _cache.clear()
    else:
        _cache.pop(key, None)
