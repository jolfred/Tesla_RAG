"""SQLite-хранилище админки (шаг 0): проекты, привязки, промпты, секреты, задачи.

Один файл storage/admin.db, создание через CREATE TABLE IF NOT EXISTS.
Без Alembic и ORM — самый простой надёжный путь.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from backend.config import STORAGE_DIR

ADMIN_DB = STORAGE_DIR / "admin.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS project_items (
    project_slug TEXT NOT NULL REFERENCES projects(slug) ON DELETE CASCADE,
    item_type TEXT NOT NULL,
    item_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_slug, item_type, item_id)
);
CREATE TABLE IF NOT EXISTS prompts (
    key TEXT PRIMARY KEY,
    text TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    project_slug TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    log_path TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT NOT NULL DEFAULT ''
);
"""


def get_connection(db_path: Path | str = ADMIN_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_admin_db(db_path: Path | str = ADMIN_DB) -> Path:
    """Создать файл БД и таблицы (идемпотентно). Возвращает путь."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return path
