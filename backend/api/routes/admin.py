"""Каркас админ-API (шаг 0): статус + список проектов.

Авторизация — Bearer admin-сессия (verify_admin_session), X-API-Key здесь
не принимаем: админка — это сайт, а не CLI.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from backend.admin import jobs as _jobs
from backend.admin import projects as _projects
from backend.admin import prompts as _prompts
from backend.admin import settings as _settings
from backend.admin.db import get_connection, init_admin_db
from backend.admin.groups import append_link, group_statuses
from backend.admin.indexing import project_composition, project_stats
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


# --- VK-группы и задачи (шаг 2) ---


@router.get("/api/v1/admin/groups")
async def admin_groups(_: dict = Depends(verify_admin_session)) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT item_id, project_slug FROM project_items WHERE item_type = 'vk_group'"
        ).fetchall()
        by_group: dict[str, list[str]] = {}
        for r in rows:
            by_group.setdefault(r["item_id"], []).append(r["project_slug"])
    finally:
        conn.close()
    groups = []
    for g in group_statuses():
        groups.append({**g, "projects": sorted(by_group.get(g["domain"], []))})
    return {"groups": groups}


@router.post("/api/v1/admin/groups", status_code=201)
async def admin_add_group(body: dict, _: dict = Depends(verify_admin_session)) -> dict:
    try:
        return append_link(body.get("url", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/v1/admin/groups/{domain}/scrape", status_code=202)
async def admin_scrape_group(
    domain: str,
    body: dict,
    bg: BackgroundTasks,
    _: dict = Depends(verify_admin_session),
) -> dict:
    urls = {g["domain"]: g["url"] for g in group_statuses()}
    if domain not in urls:
        raise HTTPException(status_code=404, detail="group not in group_links.txt")
    limit = int(body.get("limit") or 0)
    meta_only = bool(body.get("meta_only"))
    job = _jobs.create_job("scrape_meta" if meta_only else "scrape")
    argv = _jobs.python_module_cmd("scraper.main", "--url", urls[domain])
    if meta_only:
        argv.append("--meta")
    elif limit > 0:
        argv += ["--limit", str(limit)]
    bg.add_task(_jobs.run_command_job, job["id"], argv)
    return {"job_id": job["id"], "status": "queued"}


@router.get("/api/v1/admin/jobs")
async def admin_jobs(_: dict = Depends(verify_admin_session)) -> dict:
    return {"jobs": _jobs.list_jobs()}


@router.get("/api/v1/admin/jobs/{job_id}")
async def admin_job(job_id: str, _: dict = Depends(verify_admin_session)) -> dict:
    job = _jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


# --- Индексация проекта в свой namespace (шаг 3) ---


@router.post("/api/v1/admin/projects/{slug}/index", status_code=202)
async def admin_index_project(
    slug: str,
    body: dict,
    bg: BackgroundTasks,
    _: dict = Depends(verify_admin_session),
) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        exists = (
            conn.execute("SELECT 1 FROM projects WHERE slug = ?", (slug,)).fetchone()
            is not None
        )
    finally:
        conn.close()
    if not exists:
        raise HTTPException(status_code=404, detail="project not found")
    comp = project_composition(slug)
    if not comp["vk_groups"] and not comp["docs"]:
        raise HTTPException(status_code=400, detail="проект пуст: привяжите группы или документы")
    model = body.get("model") or "gigachat"
    if model not in ("gigachat", "gemma", "proxyapi"):
        raise HTTPException(status_code=400, detail="model: gigachat | gemma | proxyapi")
    extractor = body.get("extractor") or "transformer"
    if extractor not in ("legacy", "transformer"):
        raise HTTPException(status_code=400, detail="extractor: legacy | transformer")
    job = _jobs.create_job("index", project_slug=slug)
    argv = _jobs.python_module_cmd("backend.admin.run_index", slug) + [
        "--model",
        model,
        "--extractor",
        extractor,
        "--min-date",
        str(body.get("min_date") or ""),
    ]
    if body.get("force"):
        argv.append("--force")
    bg.add_task(_jobs.run_command_job, job["id"], argv)
    return {"job_id": job["id"], "status": "queued"}


@router.get("/api/v1/admin/projects/{slug}/stats")
async def admin_project_stats(slug: str, _: dict = Depends(verify_admin_session)) -> dict:
    init_admin_db()
    conn = get_connection()
    try:
        exists = (
            conn.execute("SELECT 1 FROM projects WHERE slug = ?", (slug,)).fetchone()
            is not None
        )
    finally:
        conn.close()
    if not exists:
        raise HTTPException(status_code=404, detail="project not found")
    return project_stats(slug)


# --- Тест чата по проекту (шаг 4): всегда с контекстом ---

_searcher = None


def _get_searcher():
    global _searcher
    if _searcher is None:
        from backend.rag.searcher import GraphRAGSearcher

        _searcher = GraphRAGSearcher()
    return _searcher


@router.post("/api/v1/admin/chat")
async def admin_chat(body: dict, _: dict = Depends(verify_admin_session)) -> dict:
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="пустой вопрос")
    slug = (body.get("project_slug") or "").strip() or None
    if slug:
        init_admin_db()
        conn = get_connection()
        try:
            exists = (
                conn.execute("SELECT 1 FROM projects WHERE slug = ?", (slug,)).fetchone()
                is not None
            )
        finally:
            conn.close()
        if not exists:
            raise HTTPException(status_code=404, detail="project not found")
    try:
        result = _get_searcher().search(question, include_context=True, project_slug=slug)
    except Exception as e:
        logger.error("Admin chat failed: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")
    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "mode": result.get("mode", "basic"),
        "facts_count": result.get("facts_count", 0),
        "posts_used": result.get("posts_used", 0),
        "calls": result.get("calls"),
        "trace_id": result.get("trace_id"),
    }


# --- Промпты (шаг 5) ---


@router.get("/api/v1/admin/prompts")
async def admin_prompts(_: dict = Depends(verify_admin_session)) -> dict:
    return {"prompts": _prompts.list_prompts()}


@router.put("/api/v1/admin/prompts/{key}")
async def admin_set_prompt(
    key: str, body: dict, _: dict = Depends(verify_admin_session)
) -> dict:
    try:
        _prompts.set_prompt(key, body.get("text", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/api/v1/admin/prompts/{key}/reset")
async def admin_reset_prompt(key: str, _: dict = Depends(verify_admin_session)) -> dict:
    try:
        _prompts.reset_prompt(key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "text": _prompts.defaults()[key]}


# --- Графы (шаг 6): export namespace + ссылки ---


def _browser_url() -> str:
    from backend.config import NEO4J_URI

    try:
        host = NEO4J_URI.split("://", 1)[1].split(":")[0].split("/")[0]
    except Exception:
        host = "localhost"
    return f"http://{host or 'localhost'}:7474"


@router.get("/api/v1/admin/graph/export")
async def admin_graph_export(
    project_slug: str = "",
    node_limit: int = 150,
    edge_limit: int = 300,
    _: dict = Depends(verify_admin_session),
) -> dict:
    from backend.admin.indexing import project_source_model
    from backend.rag.planner_common import MODEL as DEFAULT_MODEL

    if project_slug:
        init_admin_db()
        conn = get_connection()
        try:
            exists = (
                conn.execute(
                    "SELECT 1 FROM projects WHERE slug = ?", (project_slug,)
                ).fetchone()
                is not None
            )
        finally:
            conn.close()
        if not exists:
            raise HTTPException(status_code=404, detail="project not found")
        model = project_source_model(project_slug)
    else:
        model = DEFAULT_MODEL
    node_limit = max(10, min(node_limit, 500))
    edge_limit = max(10, min(edge_limit, 1000))
    try:
        from neo4j import GraphDatabase

        from backend.config import NEO4J_PASS, NEO4J_URI, NEO4J_USER

        driver = GraphDatabase.driver(
            NEO4J_URI,
            auth=(NEO4J_USER, NEO4J_PASS),
            connection_timeout=3,
            max_transaction_retry_time=5,
        )
        try:
            with driver.session() as session:
                nrows = session.run(
                    "MATCH (n) WHERE n.source_model = $m "
                    "RETURN coalesce(n.norm_id, n.id, n.name) AS id, "
                    "head(labels(n)) AS label, coalesce(n.name, n.id, '') AS name "
                    "LIMIT $lim",
                    m=model,
                    lim=node_limit,
                ).data()
                erows = session.run(
                    "MATCH (a)-[r]->(b) "
                    "WHERE a.source_model = $m AND b.source_model = $m "
                    "RETURN coalesce(a.norm_id, a.id, a.name) AS a, "
                    "type(r) AS rel, coalesce(b.norm_id, b.id, b.name) AS b "
                    "LIMIT $lim",
                    m=model,
                    lim=edge_limit,
                ).data()
        finally:
            driver.close()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Neo4j недоступен: {e}")
    return {
        "source_model": model,
        "browser_url": _browser_url(),
        "nodes": [{"id": str(r["id"]), "label": r["label"], "name": r["name"]} for r in nrows],
        "edges": [{"a": str(r["a"]), "rel": r["rel"], "b": str(r["b"])} for r in erows],
    }


# --- Ключи (шаг 7): без рестарта, значения наружу не отдаём ---


@router.get("/api/v1/admin/settings")
async def admin_settings(_: dict = Depends(verify_admin_session)) -> dict:
    return {"settings": _settings.list_settings()}


@router.put("/api/v1/admin/settings/{key}")
async def admin_set_setting(
    key: str, body: dict, _: dict = Depends(verify_admin_session)
) -> dict:
    try:
        _settings.set_setting(key, body.get("value", ""))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


@router.post("/api/v1/admin/settings/{key}/check")
async def admin_check_setting(key: str, _: dict = Depends(verify_admin_session)) -> dict:
    try:
        return _settings.check_setting(key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
