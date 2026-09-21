"""Проекты: CRUD + привязки файлов/групп (many-to-many)."""

from __future__ import annotations

import re
import sqlite3

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def check_slug(slug: str) -> str:
    slug = (slug or "").strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValueError("slug: латиница/цифры/дефис, 1–40 символов")
    return slug


def list_projects(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT slug, name, description, created_at FROM projects ORDER BY slug"
    ).fetchall()
    return [dict(r) for r in rows]


def create_project(conn: sqlite3.Connection, slug: str, name: str, description: str) -> dict:
    slug = check_slug(slug)
    name = (name or "").strip() or slug
    try:
        conn.execute(
            "INSERT INTO projects (slug, name, description) VALUES (?, ?, ?)",
            (slug, name, (description or "").strip()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"проект '{slug}' уже существует")
    return {"slug": slug, "name": name, "description": (description or "").strip()}


def delete_project(conn: sqlite3.Connection, slug: str) -> None:
    conn.execute("DELETE FROM project_items WHERE project_slug = ?", (slug,))
    cur = conn.execute("DELETE FROM projects WHERE slug = ?", (slug,))
    conn.commit()
    if cur.rowcount == 0:
        raise KeyError(slug)


def project_detail(conn: sqlite3.Connection, slug: str) -> dict:
    row = conn.execute(
        "SELECT slug, name, description, created_at FROM projects WHERE slug = ?",
        (slug,),
    ).fetchone()
    if row is None:
        raise KeyError(slug)
    items = conn.execute(
        "SELECT item_type, item_id FROM project_items WHERE project_slug = ? ORDER BY item_type, item_id",
        (slug,),
    ).fetchall()
    return {**dict(row), "items": [dict(r) for r in items]}


def attach_item(conn: sqlite3.Connection, slug: str, item_type: str, item_id: str) -> None:
    if item_type not in ("doc", "vk_group"):
        raise ValueError("item_type: doc | vk_group")
    item_id = (item_id or "").strip()
    if not item_id:
        raise ValueError("пустой item_id")
    if conn.execute("SELECT 1 FROM projects WHERE slug = ?", (slug,)).fetchone() is None:
        raise KeyError(slug)
    conn.execute(
        "INSERT OR IGNORE INTO project_items (project_slug, item_type, item_id) VALUES (?, ?, ?)",
        (slug, item_type, item_id),
    )
    conn.commit()


def detach_item(conn: sqlite3.Connection, slug: str, item_type: str, item_id: str) -> None:
    conn.execute(
        "DELETE FROM project_items WHERE project_slug = ? AND item_type = ? AND item_id = ?",
        (slug, item_type, item_id),
    )
    conn.commit()


def projects_of_item(conn: sqlite3.Connection, item_type: str, item_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT project_slug FROM project_items WHERE item_type = ? AND item_id = ?",
        (item_type, item_id),
    ).fetchall()
    return [r["project_slug"] for r in rows]
