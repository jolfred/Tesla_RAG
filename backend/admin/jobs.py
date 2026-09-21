"""Очередь задач админки: «добавить → поправить → запустить».

Без Celery/Redis: таблица jobs (queued/running/done/error) + запуск
сабпроцесса через FastAPI BackgroundTasks + лог storage/logs/.
Одновременно бежит не больше одной задачи. Ключи подставляются в env
сабпроцесса из admin.db (без рестарта API).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.admin.db import get_connection, init_admin_db
from backend.admin.secrets import get_secret
from backend.config import STORAGE_DIR
from backend.utils.logger import setup_logger

logger = setup_logger("admin_jobs")

LOGS_DIR = STORAGE_DIR / "logs"

# kind -> человеческое описание шаблона
KINDS = ("scrape_posts", "scrape_meta", "index")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def create_job(
    kind: str,
    project_slug: str = "",
    label: str = "",
    params: dict | None = None,
) -> dict:
    """Только положить в очередь (не запускать)."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    init_admin_db()
    job_id = uuid.uuid4().hex[:12]
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"admin_{kind}_{job_id}.log"
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO jobs (id, kind, project_slug, status, log_path, label, params)"
            " VALUES (?, ?, ?, 'queued', ?, ?, ?)",
            (job_id, kind, project_slug, str(log_path), label, json.dumps(params or {})),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": job_id, "kind": kind, "status": "queued", "log_path": str(log_path)}


def _row_to_job(row) -> dict:
    job = dict(row)
    try:
        job["params"] = json.loads(job.get("params") or "{}")
    except Exception:
        job["params"] = {}
    return job


def list_jobs(limit: int = 50) -> list[dict]:
    init_admin_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row_to_job(r) for r in rows]
    finally:
        conn.close()


def get_job(job_id: str) -> dict | None:
    init_admin_db()
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        job = _row_to_job(row)
        try:
            lines = Path(job["log_path"]).read_text(encoding="utf-8", errors="replace").splitlines()
            job["log_tail"] = "\n".join(lines[-60:])
            job["log_lines"] = len(lines)
        except OSError:
            job["log_tail"] = ""
            job["log_lines"] = 0
        return job
    finally:
        conn.close()


def any_running(except_id: str = "") -> bool:
    init_admin_db()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM jobs WHERE status = 'running' AND id <> ? LIMIT 1",
            (except_id,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def update_queued_job(job_id: str, label: str | None, params: dict | None) -> dict:
    """Правка задачи, пока она в очереди. Запущенные/готовые не трогаем."""
    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    if job["status"] != "queued":
        raise ValueError("менять можно только задачу в очереди")
    if params is not None:
        _check_params(job["kind"], params)
    conn = get_connection()
    try:
        if label is not None:
            conn.execute("UPDATE jobs SET label = ? WHERE id = ?", (label, job_id))
        if params is not None:
            conn.execute(
                "UPDATE jobs SET params = ? WHERE id = ?",
                (json.dumps(params), job_id),
            )
        conn.commit()
    finally:
        conn.close()
    return get_job(job_id) or job


def delete_job(job_id: str) -> None:
    job = get_job(job_id)
    if job is None:
        raise KeyError(job_id)
    if job["status"] == "running":
        raise ValueError("выполняющуюся задачу удалить нельзя")
    conn = get_connection()
    try:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
    finally:
        conn.close()


def prune_finished() -> int:
    init_admin_db()
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM jobs WHERE status IN ('done', 'error')")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def _check_params(kind: str, params: dict) -> None:
    if kind in ("scrape_posts", "scrape_meta"):
        if not (params.get("domain") or "").strip():
            raise ValueError("пустой domain")
        limit = int(params.get("limit") or 0)
        if limit < 0:
            raise ValueError("limit >= 0")
    elif kind == "index":
        if params.get("model") not in ("gigachat", "gemma", "proxyapi"):
            raise ValueError("model: gigachat | gemma | proxyapi")
        if params.get("extractor") not in ("legacy", "transformer"):
            raise ValueError("extractor: legacy | transformer")
    else:
        raise ValueError(f"unknown kind: {kind}")


def build_argv(job: dict) -> list[str]:
    """Команда запуска из kind+params. Бросает ValueError, если собрать нельзя."""
    kind = job["kind"]
    params = job.get("params") or {}
    _check_params(kind, params)
    if kind in ("scrape_posts", "scrape_meta"):
        from backend.admin.groups import group_statuses

        urls = {g["domain"]: g["url"] for g in group_statuses()}
        domain = params["domain"].strip()
        if domain not in urls:
            raise ValueError(f"группы '{domain}' нет в group_links.txt")
        argv = python_module_cmd("scraper.main", "--url", urls[domain])
        if kind == "scrape_meta":
            argv.append("--meta")
        elif int(params.get("limit") or 0) > 0:
            argv += ["--limit", str(int(params["limit"]))]
        return argv
    # kind == "index"
    slug = (job.get("project_slug") or params.get("slug") or "").strip()
    if not slug:
        raise ValueError("пустой проект")
    argv = python_module_cmd("backend.admin.run_index", slug) + [
        "--model", params["model"],
        "--extractor", params["extractor"],
        "--min-date", str(params.get("min_date") or ""),
    ]
    if params.get("force"):
        argv.append("--force")
    return argv
    conn = get_connection()
    try:
        cols = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))
        conn.commit()
    finally:
        conn.close()


def _set(job_id: str, **fields: str) -> None:
    conn = get_connection()
    try:
        cols = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))
        conn.commit()
    finally:
        conn.close()


def _env_with_secrets() -> dict[str, str]:
    env = dict(os.environ)
    vk = get_secret("VK_SERVICE_TOKEN") or get_secret("VK_SERVICE_TOKEN1")
    if vk:
        env["VK_SERVICE_TOKEN"] = vk
    for key in (
        "GIGACHAT_AUTH_KEY",
        "PROXYAPI_KEY",
        "PROXYAPI_BASE_URL",
        "GOOGLE_AI_STUDIO_KEY",
    ):
        val = get_secret(key)
        if val:
            env[key] = val
    return env


def run_command_job(job_id: str, argv: list[str]) -> None:
    """Тело BackgroundTask: сабпроцесс + обновление статуса."""
    _set(job_id, status="running")
    job = get_job(job_id) or {}
    log_path = job.get("log_path", "")
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(f"$ {' '.join(argv)}\n")
            fh.flush()
            proc = subprocess.run(
                argv,
                stdout=fh,
                stderr=subprocess.STDOUT,
                env=_env_with_secrets(),
                cwd=str(STORAGE_DIR.parent),
                timeout=6 * 3600,
            )
        if proc.returncode == 0:
            _set(job_id, status="done", finished_at=_now())
        else:
            # В ошибку кладём и последнюю строку лога — причина видна
            # сразу в списке, без открытия лога.
            tail = ""
            try:
                lines = Path(log_path).read_text(encoding="utf-8", errors="replace").splitlines()
                tail = lines[-1][-300:] if lines else ""
            except OSError:
                pass
            err = f"exit {proc.returncode}" + (f": {tail}" if tail else "")
            _set(job_id, status="error", error=err[:500], finished_at=_now())
    except Exception as e:
        logger.error("job %s failed: %s", job_id, e)
        _set(job_id, status="error", error=str(e)[:500], finished_at=_now())


def python_module_cmd(*args: str) -> list[str]:
    return [sys.executable, "-m", *args]
