"""Shared prompt registry, immutable-canon composition and revision history."""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from backend.admin.db import ADMIN_DB, get_connection, init_admin_db

KEYS = ("wiki_query", "wiki_extract", "wiki_merge")
TITLES = {
    "wiki_query": "Ответ по Летописи",
    "wiki_extract": "Извлечение фактов из источников",
    "wiki_merge": "Обновление статьи Летописи",
}
FILES = {
    "wiki_query": "wiki_query.md",
    "wiki_extract": "wiki_extract_en.md",
    "wiki_merge": "wiki_merge_en.md",
}
CANON_MARKER = "--- CANONICAL RULES (VERBATIM; MUST FOLLOW) ---"


def _schema_dir() -> Path:
    from backend.wiki.prompts import SCHEMA_DIR
    return SCHEMA_DIR


def defaults() -> dict[str, str]:
    """Editable stage instructions from the maintained prompt files."""
    return {key: _editable(((_schema_dir() / "prompts" / filename).read_text(encoding="utf-8")))
            for key, filename in FILES.items()}


def _editable(text: str) -> str:
    # Existing prompt files contain a snapshot of the canon. Keep all their
    # stage instructions while making the live canonical files authoritative.
    if CANON_MARKER in text:
        text = text.split(CANON_MARKER, 1)[0].rstrip()
    return text


def canonical_sections() -> list[dict[str, Any]]:
    from backend.wiki.prompts import SCHEMA_DIR
    return [{"name": name, "text": (SCHEMA_DIR / name).read_text(encoding="utf-8"), "read_only": True}
            for name in ("rules.md", "rules_mapping.md")]


def compose(key: str, stage_text: str | None = None) -> str:
    if key not in KEYS:
        raise ValueError(f"unknown prompt: {key}")
    stage = (stage_text if stage_text is not None else effective_stage(key)).strip()
    prompt = stage + "\n\n" + CANON_MARKER + "\n\n" + "\n\n".join(x["text"] for x in canonical_sections())
    if key in {"wiki_extract", "wiki_merge"}:
        skill = _editorial_skill()
        prompt += "\n\n--- EDITORIAL SKILL ---\n\n" + skill
    return prompt


def _editorial_skill() -> str:
    return (Path(__file__).resolve().parents[2] / ".opencode/skills/wiki-editorial/SKILL.md").read_text(encoding="utf-8")


def _ensure_history(conn: sqlite3.Connection) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS prompt_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT NOT NULL,
        text TEXT NOT NULL,
        revision INTEGER NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT (datetime('now'))
    )""")


def _read_stage(key: str) -> tuple[str, str, str, int]:
    """Return stage text, origin, file, history revision without initializing DB."""
    default = defaults()[key]
    if not ADMIN_DB.exists():
        return default, "default", str(_schema_dir() / "prompts" / FILES[key]), 0
    try:
        conn = get_connection()
        try:
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            row = conn.execute("SELECT text FROM prompts WHERE key=?", (key,)).fetchone() if "prompts" in tables else None
            text = _editable(str(row["text"])) if row and row["text"] else default
            hist = conn.execute("SELECT MAX(revision) AS rev FROM prompt_history WHERE key=?", (key,)).fetchone() if "prompt_history" in tables else None
            revision = int(hist["rev"] or 0) if hist else 0
        finally:
            conn.close()
        return text, ("admin_override" if row and row["text"] else "default"), (str(ADMIN_DB) if row and row["text"] else str(_schema_dir() / "prompts" / FILES[key])), revision
    except sqlite3.Error:
        return default, "default", str(_schema_dir() / "prompts" / FILES[key]), 0


def effective_stage(key: str) -> str:
    if key not in KEYS:
        raise ValueError(f"unknown prompt: {key}")
    return _read_stage(key)[0]


def effective_revision(key: str) -> str:
    return hashlib.sha256(effective_stage(key).encode("utf-8")).hexdigest()


def effective_prompt(key: str) -> dict[str, Any]:
    stage, origin, filename, rev = _read_stage(key)
    return {"key": key, "title": TITLES[key], "text": stage,
            "effective_prompt": compose(key, stage), "effective_origin": origin,
            "effective_file": filename, "revision": hashlib.sha256(stage.encode("utf-8")).hexdigest(),
            "history_revision": rev, "updated_at": _updated_at(key),
            "canonical_sections": canonical_sections()}


def _updated_at(key: str) -> str:
    if not ADMIN_DB.exists(): return ""
    try:
        conn = get_connection()
        try:
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            row = conn.execute("SELECT updated_at FROM prompts WHERE key=?", (key,)).fetchone() if "prompts" in tables else None
            if row:
                return str(row["updated_at"])
            if "prompt_history" in tables:
                historical = conn.execute("SELECT created_at FROM prompt_history WHERE key=? ORDER BY revision DESC LIMIT 1", (key,)).fetchone()
                return str(historical["created_at"]) if historical else ""
            return ""
        finally: conn.close()
    except sqlite3.Error: return ""


def get_prompt(key: str) -> str:
    """Effective prompt consumed by query and ingestion code."""
    if key in KEYS:
        return compose(key)
    # Retain compatibility for existing non-Wiki prompt consumers.
    if not ADMIN_DB.exists():
        raise ValueError(f"unknown prompt: {key}")
    try:
        conn = get_connection()
        try: row = conn.execute("SELECT text FROM prompts WHERE key=?", (key,)).fetchone()
        finally: conn.close()
        if row: return str(row["text"])
    except sqlite3.Error: pass
    raise ValueError(f"unknown prompt: {key}")


def list_prompts() -> list[dict[str, Any]]:
    return [effective_prompt(key) for key in KEYS]


class PromptRevisionConflict(Exception):
    def __init__(self, current_revision: str):
        self.current_revision = current_revision


def save_prompt(key: str, text: str, expected_revision: str, reason: str = "") -> dict[str, Any]:
    if key not in KEYS: raise ValueError(f"unknown prompt: {key}")
    if not isinstance(text, str) or not text.strip(): raise ValueError("пустой текст")
    if not isinstance(expected_revision, str) or not expected_revision:
        raise ValueError("expected_revision обязателен")
    if CANON_MARKER in text: text = _editable(text)
    init_admin_db()
    conn = get_connection()
    try:
        _ensure_history(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT text FROM prompts WHERE key=?", (key,)).fetchone()
        current = _editable(str(row["text"])) if row and row["text"] else defaults()[key]
        current_revision = hashlib.sha256(current.encode("utf-8")).hexdigest()
        if expected_revision and expected_revision != current_revision:
            conn.rollback(); raise PromptRevisionConflict(current_revision)
        latest = conn.execute("SELECT MAX(revision) AS rev FROM prompt_history WHERE key=?", (key,)).fetchone()["rev"] or 0
        if int(latest) == 0:
            # Preserve the exact pre-editor version too, including the
            # registered default or an override created before history existed.
            conn.execute("INSERT INTO prompt_history(key,text,revision,reason) VALUES(?,?,1,?)",
                         (key, current, "Initial version before revision history"))
            latest = 1
        revision = int(latest) + 1
        conn.execute("INSERT INTO prompt_history(key,text,revision,reason) VALUES(?,?,?,?)", (key, text, revision, reason.strip()))
        conn.execute("INSERT INTO prompts(key,text,updated_at) VALUES(?,?,datetime('now')) ON CONFLICT(key) DO UPDATE SET text=excluded.text,updated_at=datetime('now')", (key, text))
        conn.commit()
    finally: conn.close()
    return effective_prompt(key)


def restore_prompt(key: str, history_id: int, expected_revision: str, reason: str = "") -> dict[str, Any]:
    if key not in KEYS: raise ValueError(f"unknown prompt: {key}")
    if not isinstance(expected_revision, str) or not expected_revision:
        raise ValueError("expected_revision обязателен")
    conn = get_connection()
    try:
        _ensure_history(conn)
        row = conn.execute("SELECT text FROM prompt_history WHERE id=? AND key=?", (history_id, key)).fetchone()
        if not row: raise KeyError("prompt history entry not found")
        text = str(row["text"])
    finally: conn.close()
    return save_prompt(key, text, expected_revision, reason or f"Restore history entry {history_id}")


def prompt_history(key: str) -> list[dict[str, Any]]:
    if key not in KEYS: raise ValueError(f"unknown prompt: {key}")
    if not ADMIN_DB.exists(): return []
    try:
        conn = get_connection()
        try:
            if "prompt_history" not in {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}: return []
            return [dict(r) for r in conn.execute("SELECT id,key,text,revision,reason,created_at FROM prompt_history WHERE key=? ORDER BY revision DESC", (key,))]
        finally: conn.close()
    except sqlite3.Error: return []


def set_prompt(key: str, text: str) -> None:
    """Legacy admin endpoint compatibility; version every successful save."""
    save_prompt(key, text, effective_revision(key), "Legacy prompt editor save")


def reset_prompt(key: str) -> None:
    if key not in KEYS: raise ValueError(f"unknown prompt: {key}")
    reset_prompt_versioned(key, effective_revision(key))


def reset_prompt_versioned(key: str, expected_revision: str) -> dict[str, Any]:
    """Snapshot the prior/default text and clear the DB override with CAS."""
    if key not in KEYS: raise ValueError(f"unknown prompt: {key}")
    if not isinstance(expected_revision, str) or not expected_revision:
        raise ValueError("expected_revision обязателен")
    init_admin_db()
    conn = get_connection()
    try:
        _ensure_history(conn)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT text FROM prompts WHERE key=?", (key,)).fetchone()
        current = _editable(str(row["text"])) if row and row["text"] else defaults()[key]
        current_revision = hashlib.sha256(current.encode("utf-8")).hexdigest()
        if expected_revision != current_revision:
            conn.rollback()
            raise PromptRevisionConflict(current_revision)
        latest = conn.execute("SELECT MAX(revision) AS rev FROM prompt_history WHERE key=?", (key,)).fetchone()["rev"] or 0
        if int(latest) == 0:
            conn.execute("INSERT INTO prompt_history(key,text,revision,reason) VALUES(?,?,1,?)",
                         (key, current, "Initial version before revision history"))
            latest = 1
        default = defaults()[key]
        revision = int(latest) + 1
        conn.execute("INSERT INTO prompt_history(key,text,revision,reason) VALUES(?,?,?,?)",
                     (key, default, revision, "Reset to registered default"))
        conn.execute("DELETE FROM prompts WHERE key=?", (key,))
        conn.commit()
    finally:
        conn.close()
    return effective_prompt(key)
