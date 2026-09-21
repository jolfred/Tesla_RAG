"""Фоновые задачи админки: запуск CLI-скриптов сабпроцессом с логом в файл.

Без Celery/Redis: FastAPI BackgroundTasks + таблица jobs + лог storage/logs/.
Статус обновляется в БД по завершении. Ключи подставляются в env
сабпроцесса из admin.db (без рестарта API).
"""

from __future__ import annotations

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


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def create_job(kind: str, project_slug: str = "") -> dict:
    init_admin_db()
    job_id = uuid.uuid4().hex[:12]
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"admin_{kind}_{job_id}.log"
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO jobs (id, kind, project_slug, status, log_path) VALUES (?, ?, ?, 'queued', ?)",
            (job_id, kind, project_slug, str(log_path)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"id": job_id, "kind": kind, "log_path": str(log_path)}


def list_jobs(limit: int = 30) -> list[dict]:
    init_admin_db()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_job(job_id: str) -> dict | None:
    init_admin_db()
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        job = dict(row)
        try:
            text = Path(job["log_path"]).read_text(encoding="utf-8", errors="replace")
            job["log_tail"] = "\n".join(text.splitlines()[-40:])
        except OSError:
            job["log_tail"] = ""
        return job
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
            _set(job_id, status="error", error=f"exit {proc.returncode}", finished_at=_now())
    except Exception as e:
        logger.error("job %s failed: %s", job_id, e)
        _set(job_id, status="error", error=str(e)[:500], finished_at=_now())


def python_module_cmd(*args: str) -> list[str]:
    return [sys.executable, "-m", *args]
