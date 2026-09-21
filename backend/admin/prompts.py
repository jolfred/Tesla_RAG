"""Промпты всех уровней: чтение с fallback на константы кода.

Код читает промпт через get_prompt(key): override из admin.db, иначе
дефолт из кода. Чтение никогда не создаёт БД (нет файла — дефолт).
Запись/сброс — только из админ-роутера.
"""

from __future__ import annotations

from backend.admin.db import ADMIN_DB, get_connection

KEYS = (
    "answer_base",
    "answer_narrative",
    "answer_global_extra",
    "plan_prompt",
    "extract_system",
)

TITLES = {
    "answer_base": "Ответ — базовый системный промпт",
    "answer_narrative": "Ответ — нарратив для enumerable-блоков",
    "answer_global_extra": "Ответ — добавка для global-режима",
    "plan_prompt": "План — классификатор интента и слотов",
    "extract_system": "Индексация — извлечение графа из поста",
}

_defaults: dict[str, str] | None = None


def defaults() -> dict[str, str]:
    """Дефолты = текущие константы кода (ленивый импорт, без циклов)."""
    global _defaults
    if _defaults is None:
        from backend.indexer.prompts import SYSTEM_PROMPT
        from backend.rag.answer_generator import (
            BASE_PROMPT,
            GLOBAL_EXTRAS,
            NARRATIVE_PROMPT,
        )
        from backend.rag.query_planner import PLAN_PROMPT

        _defaults = {
            "answer_base": BASE_PROMPT,
            "answer_narrative": NARRATIVE_PROMPT,
            "answer_global_extra": GLOBAL_EXTRAS,
            "plan_prompt": PLAN_PROMPT,
            "extract_system": SYSTEM_PROMPT,
        }
    return _defaults


def get_prompt(key: str) -> str:
    """Текст промпта: override из БД, иначе дефолт. Никогда не падает."""
    try:
        default = defaults()[key]
    except KeyError:
        raise ValueError(f"unknown prompt: {key}")
    if not ADMIN_DB.exists():
        return default
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT text FROM prompts WHERE key = ?", (key,)
            ).fetchone()
        finally:
            conn.close()
        if row and row["text"]:
            return str(row["text"])
    except Exception:
        pass
    return default


def list_prompts() -> list[dict]:
    from backend.admin.db import init_admin_db

    init_admin_db()
    conn = get_connection()
    try:
        rows = {r["key"]: r["text"] for r in conn.execute("SELECT key, text FROM prompts")}
        meta = {r["key"]: r["updated_at"] for r in conn.execute("SELECT key, updated_at FROM prompts")}
    finally:
        conn.close()
    out = []
    for key in KEYS:
        out.append(
            {
                "key": key,
                "title": TITLES[key],
                "text": rows.get(key) or defaults()[key],
                "custom": key in rows,
                "updated_at": meta.get(key, ""),
            }
        )
    return out


def set_prompt(key: str, text: str) -> None:
    if key not in KEYS:
        raise ValueError(f"unknown prompt: {key}")
    if not (text or "").strip():
        raise ValueError("пустой текст")
    from backend.admin.db import init_admin_db

    init_admin_db()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO prompts (key, text, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET text = excluded.text, updated_at = datetime('now')",
            (key, text),
        )
        conn.commit()
    finally:
        conn.close()


def reset_prompt(key: str) -> None:
    if key not in KEYS:
        raise ValueError(f"unknown prompt: {key}")
    from backend.admin.db import init_admin_db

    init_admin_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM prompts WHERE key = ?", (key,))
        conn.commit()
    finally:
        conn.close()
