"""Каркас админ-API (шаг 0): статус + список проектов.

Авторизация — Bearer admin-сессия (verify_admin_session), X-API-Key здесь
не принимаем: админка — это сайт, а не CLI.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.admin.db import get_connection, init_admin_db
from backend.api.auth import verify_admin_session

router = APIRouter()


@router.get("/api/v1/admin/status")
async def admin_status(_: dict = Depends(verify_admin_session)) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        projects = conn.execute("SELECT COUNT(*) AS n FROM projects").fetchone()["n"]
        queued = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE status IN ('queued','running')"
        ).fetchone()["n"]
    finally:
        conn.close()
    return {"status": "ok", "projects_count": projects, "jobs_active": queued}


@router.get("/api/v1/admin/projects")
async def admin_projects(_: dict = Depends(verify_admin_session)) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT slug, name, description, created_at FROM projects ORDER BY slug"
        ).fetchall()
    finally:
        conn.close()
    return {
        "projects": [
            {
                "slug": r["slug"],
                "name": r["name"],
                "description": r["description"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    }
