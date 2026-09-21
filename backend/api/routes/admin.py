"""Каркас админ-API (шаг 0): статус + список проектов.

Авторизация — Bearer admin-сессия (verify_admin_session), X-API-Key здесь
не принимаем: админка — это сайт, а не CLI.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from backend.admin import projects as _projects
from backend.admin.db import get_connection, init_admin_db
from backend.api.auth import verify_admin_session
from backend.config import DOCUMENTS_DIR
from backend.utils.logger import setup_logger

logger = setup_logger("admin_route")

router = APIRouter()

_ALLOWED_EXTS = {"pdf", "docx", "txt", "json"}


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


# --- Проекты (шаг 1) ---


@router.get("/api/v1/admin/projects")
async def admin_projects(_: dict = Depends(verify_admin_session)) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        return {"projects": _projects.list_projects(conn)}
    finally:
        conn.close()


@router.post("/api/v1/admin/projects", status_code=201)
async def admin_create_project(
    body: dict, _: dict = Depends(verify_admin_session)
) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        try:
            proj = _projects.create_project(
                conn,
                body.get("slug", ""),
                body.get("name", ""),
                body.get("description", ""),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return proj
    finally:
        conn.close()


@router.get("/api/v1/admin/projects/{slug}")
async def admin_project_detail(slug: str, _: dict = Depends(verify_admin_session)) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        try:
            return _projects.project_detail(conn, slug)
        except KeyError:
            raise HTTPException(status_code=404, detail="project not found")
    finally:
        conn.close()


@router.delete("/api/v1/admin/projects/{slug}")
async def admin_delete_project(slug: str, _: dict = Depends(verify_admin_session)) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        try:
            _projects.delete_project(conn, slug)
        except KeyError:
            raise HTTPException(status_code=404, detail="project not found")
        return {"ok": True}
    finally:
        conn.close()


@router.post("/api/v1/admin/projects/{slug}/items", status_code=201)
async def admin_attach_item(
    slug: str, body: dict, _: dict = Depends(verify_admin_session)
) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        try:
            _projects.attach_item(conn, slug, body.get("item_type", ""), body.get("item_id", ""))
        except KeyError:
            raise HTTPException(status_code=404, detail="project not found")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}
    finally:
        conn.close()


@router.delete("/api/v1/admin/projects/{slug}/items")
async def admin_detach_item(
    slug: str, item_type: str, item_id: str, _: dict = Depends(verify_admin_session)
) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        _projects.detach_item(conn, slug, item_type, item_id)
        return {"ok": True}
    finally:
        conn.close()


# --- Документы (шаг 1): список + загрузка, мета в admin.db ---


def _doc_files() -> list[Path]:
    if not DOCUMENTS_DIR.exists():
        return []
    return sorted(
        [p for p in DOCUMENTS_DIR.iterdir() if p.is_file() and not p.name.startswith(".")]
    )


@router.get("/api/v1/admin/documents")
async def admin_documents(_: dict = Depends(verify_admin_session)) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        meta = {
            r["doc_id"]: dict(r)
            for r in conn.execute("SELECT * FROM documents_meta").fetchall()
        }
        proj_rows = conn.execute(
            "SELECT item_id, project_slug FROM project_items WHERE item_type = 'doc'"
        ).fetchall()
        by_doc: dict[str, list[str]] = {}
        for r in proj_rows:
            by_doc.setdefault(r["item_id"], []).append(r["project_slug"])
    finally:
        conn.close()
    docs = []
    for p in _doc_files():
        doc_id = p.stem.split("__")[0]
        m = meta.get(doc_id, {})
        docs.append(
            {
                "doc_id": doc_id,
                "filename": m.get("filename") or p.name,
                "title": m.get("title") or m.get("filename") or p.name,
                "size": p.stat().st_size,
                "projects": sorted(by_doc.get(doc_id, [])),
            }
        )
    return {"documents": docs}


@router.post("/api/v1/admin/documents/upload", status_code=201)
async def admin_upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    _: dict = Depends(verify_admin_session),
) -> dict:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    fname = file.filename or "untitled"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported format: .{ext}")
    doc_id = str(uuid.uuid4())
    save_path = DOCUMENTS_DIR / f"{doc_id}.{ext}"
    save_path.write_bytes(content)
    doc_title = title.strip() or fname
    if ext == "json":
        try:
            data = json.loads(content)
            doc_title = data.get("title") or data.get("id") or doc_title
        except Exception:
            pass
    init_admin_db()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO documents_meta (doc_id, filename, title, size) VALUES (?, ?, ?, ?)",
            (doc_id, fname, doc_title, len(content)),
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("Admin uploaded %s (%d bytes)", save_path.name, len(content))
    return {"doc_id": doc_id, "title": doc_title, "status": "uploaded"}
