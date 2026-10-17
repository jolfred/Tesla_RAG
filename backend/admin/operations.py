"""Durable, source-only operations inbox and daily VK collection scheduler.

This module never calls an LLM or writes Wiki pages. The worker only fetches
VK posts, extracts uploaded document text, and persists source records/inbox
states. Compilation remains a separate, manually authorized workflow.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime, time as daytime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.config import BASE_DIR, DOCUMENTS_DIR, STORAGE_DIR

DB_PATH = STORAGE_DIR / "admin_operations.db"
TZ_NAME = "Europe/Moscow"
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$")
_DOC_ID_RE = re.compile(r"^[a-f0-9-]{36}$")
_EXCLUDED_VK_DOMAINS = {"kgeu_official", "rso_rt", "spoyunost"}
_worker_lock = threading.Lock()
_worker_thread: threading.Thread | None = None
_worker_stop = threading.Event()
_worker_wake = threading.Event()


def _now() -> str:
    return datetime.now(ZoneInfo(TZ_NAME)).isoformat(timespec="seconds")


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=FULL")
    con.executescript("""
      CREATE TABLE IF NOT EXISTS sources(
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, domain TEXT, url TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '', file_path TEXT, active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL, last_collected_at TEXT, UNIQUE(kind,domain), UNIQUE(kind,file_path));
      CREATE TABLE IF NOT EXISTS operations_jobs(
        id TEXT PRIMARY KEY, kind TEXT NOT NULL, source_id TEXT NOT NULL,
        status TEXT NOT NULL, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
        attempts INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
        result_json TEXT NOT NULL DEFAULT '{}', log TEXT NOT NULL DEFAULT '',
        retry_of TEXT, scheduled_for TEXT);
      CREATE INDEX IF NOT EXISTS operations_jobs_queue ON operations_jobs(status,created_at);
      CREATE TABLE IF NOT EXISTS inbox(
        id TEXT PRIMARY KEY, source_id TEXT NOT NULL, source_kind TEXT NOT NULL,
        external_id TEXT NOT NULL, content_sha256 TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
        text TEXT NOT NULL, published_at TEXT, source_url TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}', state TEXT NOT NULL DEFAULT 'queued',
        collected_at TEXT NOT NULL, job_id TEXT,
        UNIQUE(source_id,external_id,content_sha256));
      CREATE INDEX IF NOT EXISTS inbox_state_date ON inbox(state,collected_at DESC);
      CREATE TABLE IF NOT EXISTS schedule(
        singleton INTEGER PRIMARY KEY CHECK(singleton=1), enabled INTEGER NOT NULL DEFAULT 0,
        local_time TEXT NOT NULL DEFAULT '08:00', timezone TEXT NOT NULL DEFAULT 'Europe/Moscow',
        source_ids_json TEXT NOT NULL DEFAULT '[]', last_run_date TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS uploaded_documents(
        doc_id TEXT PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL, created_at TEXT NOT NULL);
      INSERT OR IGNORE INTO schedule(singleton) VALUES(1);
    """)
    source_cols = {r[1] for r in con.execute("PRAGMA table_info(sources)")}
    if "last_collected_at" not in source_cols:
        con.execute("ALTER TABLE sources ADD COLUMN last_collected_at TEXT")
    con.commit()
    # The ledger can contain unpublished personal information from uploaded
    # documents. Keep SQLite files private on POSIX deployments.
    for private_path in (db_path, Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
        try:
            if private_path.exists(): os.chmod(private_path, 0o600)
        except OSError:
            pass
    return con


def _domain_and_url(value: str) -> tuple[str, str]:
    parsed = urlparse((value or "").strip())
    if parsed.scheme != "https" or parsed.hostname not in {"vk.com", "www.vk.com", "vk.ru", "www.vk.ru", "m.vk.com"}:
        raise ValueError("Укажите HTTPS-ссылку на группу VK")
    if parsed.username or parsed.password or parsed.port or parsed.query or parsed.fragment:
        raise ValueError("Ссылка на VK-группу не должна содержать логин, порт, query или fragment")
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) != 1 or not _DOMAIN_RE.fullmatch(parts[0]):
        raise ValueError("Не удалось определить домен VK-группы")
    domain = parts[0].lower()
    if re.fullmatch(r"wall-?\d+_\d+", domain, re.IGNORECASE):
        raise ValueError("Ссылка на публикацию VK принимается через форму ссылки на пост")
    return domain, f"https://vk.com/{domain}"


def add_vk_source(url: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    domain, canonical = _domain_and_url(url)
    if domain.casefold() in _EXCLUDED_VK_DOMAINS:
        raise ValueError("Этот источник исключён из Wiki-корпуса")
    con = connect(db_path)
    try:
        source_id = "vk:" + domain
        baseline = _latest_timestamp(STORAGE_DIR / "posts" / f"posts_{domain}.jsonl")
        baseline_value = baseline.isoformat() if baseline else None
        con.execute("INSERT OR IGNORE INTO sources(id,kind,domain,url,title,created_at,last_collected_at) VALUES(?,?,?,?,?,?,?)",
                    (source_id, "vk", domain, canonical, domain, _now(), baseline_value))
        row = con.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if row["url"] != canonical:
            raise ValueError("Источник с таким доменом уже зарегистрирован с другой ссылкой")
        con.commit()
        return dict(row)
    finally:
        con.close()


def import_existing_vk_sources(links_path: Path = STORAGE_DIR / "posts" / "group_links.txt",
                               db_path: Path = DB_PATH) -> dict[str, Any]:
    """Import active VK group links and local titles without contacting VK."""
    groups_dir = STORAGE_DIR / "groups"
    imported: list[str] = []
    existing: list[str] = []
    skipped: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if not links_path.is_file():
        raise FileNotFoundError(links_path)
    for line_number, raw_line in enumerate(links_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        if "vk.com/" not in value and "vk.ru/" not in value:
            continue
        try:
            domain, _ = _domain_and_url(value)
            # Preserve explicit legacy exclusion policy even if an excluded
            # domain is accidentally uncommented in the link file.
            if domain in _EXCLUDED_VK_DOMAINS:
                skipped.append({"line": str(line_number), "domain": domain, "reason": "excluded"})
                continue
            con = connect(db_path)
            try:
                was_present = con.execute("SELECT 1 FROM sources WHERE id=?", (f"vk:{domain}",)).fetchone() is not None
            finally:
                con.close()
            metadata_path = groups_dir / f"groups_{domain}.json"
            title = ""
            if metadata_path.is_file():
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    title = str(metadata.get("name") or "").strip()
                except (OSError, json.JSONDecodeError) as exc:
                    warnings.append({"domain": domain, "reason": f"group title metadata unavailable: {type(exc).__name__}"})
            source = add_vk_source(value, db_path)
            if title:
                con = connect(db_path)
                try:
                    con.execute("UPDATE sources SET title=? WHERE id=?", (title, source["id"]))
                    con.commit()
                finally:
                    con.close()
            (existing if was_present else imported).append(source["id"])
        except (ValueError, json.JSONDecodeError) as exc:
            skipped.append({"line": str(line_number), "value": value[:200], "reason": str(exc)})
    return {"imported": imported, "already_present": existing, "skipped": skipped,
            "warnings": warnings, "total": len(imported) + len(existing)}


def list_sources(db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    con = connect(db_path)
    try:
        return [dict(r) for r in con.execute("SELECT * FROM sources ORDER BY kind,domain,title")]
    finally:
        con.close()


def _extract_document(path: Path, documents_dir: Path = DOCUMENTS_DIR) -> tuple[str, str]:
    if not path.is_file() or not path.resolve().is_relative_to(documents_dir.resolve()):
        raise ValueError("Файл документа не найден")
    size = path.stat().st_size
    if size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"Файл превышает лимит {MAX_DOCUMENT_BYTES // (1024*1024)} МБ")
    ext = path.suffix.casefold()
    if ext in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8-sig")
        method = "utf-8 text"
    elif ext == ".json":
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        text = json.dumps(data, ensure_ascii=False, indent=2)
        method = "JSON source"
    elif ext == ".pdf":
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            page_texts = [page.extract_text(layout=False) or "" for page in pdf.pages]
        if not any(page_text.strip() for page_text in page_texts):
            raise ValueError("В PDF нет текстового слоя; OCR не выполнялся")
        chunks = [f"Страница {number}\n{page_text}" for number, page_text in enumerate(page_texts, 1)]
        text = "\n\n".join(chunks)
        method = f"PDF text ({len(chunks)} pages)"
    elif ext == ".docx":
        from docx import Document
        document = Document(path)
        chunks = []
        for block in document.iter_inner_content():
            if hasattr(block, "rows"):
                chunks.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
            elif getattr(block, "text", ""):
                chunks.append(block.text)
        text = "\n".join(chunks)
        method = "DOCX paragraphs and tables"
    else:
        raise ValueError(f"Формат {ext or '(без расширения)'} не поддерживается")
    if not text.strip():
        raise ValueError("В документе не найден извлекаемый текст; источник не добавлен")
    return text, method


def save_document_upload(filename: str, content: bytes, documents_dir: Path = DOCUMENTS_DIR,
                         title: str | None = None, db_path: Path = DB_PATH) -> dict[str, Any]:
    """Persist one bounded upload for later explicit inbox preparation."""
    suffix = Path(filename or "").suffix.casefold()
    if suffix not in {".pdf", ".docx", ".txt", ".json", ".md"}:
        raise ValueError("Поддерживаются только PDF, DOCX, TXT, JSON и MD")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"Файл превышает лимит {MAX_DOCUMENT_BYTES // (1024*1024)} МБ")
    documents_dir.mkdir(parents=True, exist_ok=True)
    doc_id = str(uuid.uuid4())
    path = documents_dir / f"{doc_id}{suffix}"
    # Exclusive creation protects against accidental replacement if the ID
    # generator ever returns a collision.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
        os.fchmod(stream.fileno(), 0o600)
    display_title = (title or Path(filename).name).strip()[:255] or Path(filename).name[:255]
    con = connect(db_path)
    try:
        con.execute("INSERT INTO uploaded_documents(doc_id,title,filename,created_at) VALUES(?,?,?,?)",
                    (doc_id, display_title, Path(filename).name[:255], _now()))
        con.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        con.close()
    return {"id": doc_id, "title": display_title, "status": "uploaded", "bytes": len(content)}


def prepare_document(doc_id: str, documents_dir: Path = DOCUMENTS_DIR, db_path: Path = DB_PATH) -> dict[str, Any]:
    if not _DOC_ID_RE.fullmatch(doc_id):
        raise ValueError("Некорректный ID документа")
    matches = sorted(documents_dir.glob(f"{doc_id}.*"))
    matches = [p for p in matches if p.is_file() and p.resolve().is_relative_to(documents_dir.resolve())]
    if len(matches) != 1:
        raise ValueError("Ожидался один сохранённый файл документа")
    path = matches[0]
    text, method = _extract_document(path, documents_dir)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    source_id = f"document:{doc_id}"
    source_url = f"document://{doc_id}"
    metadata = {"filename": path.name, "extractor": method, "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "text_sha256": content_hash, "text_chars": len(text)}
    con = connect(db_path)
    try:
        uploaded = con.execute("SELECT title FROM uploaded_documents WHERE doc_id=?", (doc_id,)).fetchone()
        title = uploaded["title"] if uploaded else path.name
        con.execute("INSERT OR IGNORE INTO sources(id,kind,domain,url,title,file_path,created_at) VALUES(?,?,?,?,?,?,?)",
                    (source_id, "document", None, source_url, title, str(path), _now()))
        item_id = str(uuid.uuid4())
        cur = con.execute("INSERT OR IGNORE INTO inbox(id,source_id,source_kind,external_id,content_sha256,title,text,published_at,source_url,metadata_json,state,collected_at) VALUES(?,?,?,?,?,?,?,?,?,?, 'queued',?)",
                          (item_id, source_id, "document", source_id, content_hash, title, text, None, source_url,
                           json.dumps(metadata, ensure_ascii=False), _now()))
        if cur.rowcount == 0:
            row = con.execute("SELECT id,state FROM inbox WHERE source_id=? AND external_id=? AND content_sha256=?",
                              (source_id, source_id, content_hash)).fetchone()
            con.commit()
            return {"source_id": source_id, "inbox_id": row["id"], "state": row["state"], "duplicate": True, **metadata}
        con.commit()
        return {"source_id": source_id, "inbox_id": item_id, "state": "queued", "duplicate": False, **metadata}
    finally:
        con.close()


def create_vk_job(source_id: str, limit: int = 0, db_path: Path = DB_PATH,
                  *, scheduled_for: str | None = None, retry_of: str | None = None) -> dict[str, Any]:
    if not isinstance(limit, int) or limit < 0 or limit > 10000:
        raise ValueError("limit должен быть от 0 до 10000 (0 — все новые посты)")
    con = connect(db_path)
    try:
        source = con.execute("SELECT id,kind,active FROM sources WHERE id=?", (source_id,)).fetchone()
        if not source or source["kind"] != "vk" or not source["active"]:
            raise KeyError(source_id)
        params = json.dumps({"limit": limit}, ensure_ascii=False)
        job_id = uuid.uuid4().hex
        con.execute("INSERT INTO operations_jobs(id,kind,source_id,status,created_at,result_json,retry_of,scheduled_for,log) VALUES(?, 'vk_fetch', ?, 'queued', ?, ?, ?, ?, ?)",
                    (job_id, source_id, _now(), params, retry_of, scheduled_for, ""))
        con.commit()
        _worker_wake.set()
        return get_job(job_id, db_path)
    finally:
        con.close()


def create_vk_post_source(url: str, db_path: Path = DB_PATH) -> tuple[dict[str, Any], dict[str, Any]]:
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https" or parsed.hostname not in {"vk.com", "www.vk.com", "vk.ru", "www.vk.ru", "m.vk.com"}:
        raise ValueError("Укажите HTTPS-ссылку на публикацию VK")
    if parsed.username or parsed.password or parsed.port:
        raise ValueError("Ссылка не должна содержать логин или порт")
    wall = ""
    path_match = re.fullmatch(r"/wall(-?\d+_\d+)/?", parsed.path)
    if path_match:
        wall = "wall" + path_match.group(1)
    if not wall:
        wall = parse_qs(parsed.query).get("w", [""])[0]
    match = re.fullmatch(r"wall(-?\d+)_(\d+)", wall)
    if not match:
        raise ValueError("Ссылка должна указывать на конкретную запись VK (wall<owner>_<post>)")
    canonical = f"https://vk.com/{wall}"
    source_id = f"vkpost:{wall}"
    con = connect(db_path)
    try:
        con.execute("INSERT OR IGNORE INTO sources(id,kind,domain,url,title,created_at) VALUES(?, 'vk_post', ?, ?, ?, ?)",
                    (source_id, wall, canonical, f"Публикация {wall}", _now()))
        con.commit()
    finally:
        con.close()
    source = next(row for row in list_sources(db_path) if row["id"] == source_id)
    con = connect(db_path)
    try:
        job_id = uuid.uuid4().hex
        con.execute("INSERT INTO operations_jobs(id,kind,source_id,status,created_at,result_json) VALUES(?, 'vk_post_fetch', ?, 'queued', ?, '{}')",
                    (job_id, source_id, _now()))
        con.commit()
    finally:
        con.close()
    _worker_wake.set()
    return source, get_job(job_id, db_path)


def get_job(job_id: str, db_path: Path = DB_PATH) -> dict[str, Any] | None:
    con = connect(db_path)
    try:
        row = con.execute("SELECT j.*,s.title AS source_title,s.url AS source_url FROM operations_jobs j LEFT JOIN sources s ON s.id=j.source_id WHERE j.id=?", (job_id,)).fetchone()
        if not row:
            return None
        job = dict(row)
        try: job["result"] = json.loads(job.pop("result_json"))
        except ValueError: job["result"] = {}
        return job
    finally:
        con.close()


def list_jobs(limit: int = 50, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    if not 1 <= limit <= 200: raise ValueError("limit должен быть от 1 до 200")
    con = connect(db_path)
    try:
        ids = [r[0] for r in con.execute("SELECT id FROM operations_jobs ORDER BY created_at DESC LIMIT ?", (limit,))]
    finally: con.close()
    return [get_job(j, db_path) for j in ids]


def retry_job(job_id: str, db_path: Path = DB_PATH) -> dict[str, Any]:
    old = get_job(job_id, db_path)
    if not old: raise KeyError(job_id)
    if old["kind"] not in {"vk_fetch", "vk_post_fetch"}: raise ValueError("Тип задачи нельзя повторить")
    if old["status"] not in {"failed", "interrupted"}: raise ValueError("Повторить можно только неудачную или прерванную задачу")
    if old["kind"] == "vk_post_fetch":
        con = connect(db_path)
        try:
            retry_id = uuid.uuid4().hex
            con.execute("INSERT INTO operations_jobs(id,kind,source_id,status,created_at,result_json,retry_of) VALUES(?, 'vk_post_fetch', ?, 'queued', ?, '{}', ?)",
                        (retry_id, old["source_id"], _now(), job_id))
            con.commit()
        finally: con.close()
        _worker_wake.set()
        return get_job(retry_id, db_path)
    return create_vk_job(old["source_id"], int(old["result"].get("limit", 0)), db_path, retry_of=job_id)


def set_schedule(enabled: bool, local_time: str, timezone: str, source_ids: list[str], db_path: Path = DB_PATH) -> dict[str, Any]:
    if timezone != TZ_NAME:
        raise ValueError("Разрешённый часовой пояс: Europe/Moscow")
    try:
        daytime.fromisoformat(local_time)
        if len(local_time) != 5: raise ValueError
    except ValueError:
        raise ValueError("local_time должен иметь формат HH:MM")
    try: ZoneInfo(timezone)
    except ZoneInfoNotFoundError: raise ValueError("Часовой пояс недоступен")
    if not isinstance(source_ids, list) or len(set(source_ids)) != len(source_ids):
        raise ValueError("source_ids должен быть списком уникальных ID")
    con = connect(db_path)
    try:
        if source_ids:
            marks = ",".join("?" for _ in source_ids)
            rows = con.execute(f"SELECT id FROM sources WHERE kind='vk' AND active=1 AND id IN ({marks})", source_ids).fetchall()
            if {r[0] for r in rows} != set(source_ids): raise ValueError("source_ids содержит неизвестный VK-источник")
        con.execute("UPDATE schedule SET enabled=?,local_time=?,timezone=?,source_ids_json=? WHERE singleton=1",
                    (int(bool(enabled)), local_time, timezone, json.dumps(source_ids)))
        con.commit()
        return get_schedule(db_path)
    finally: con.close()


def get_schedule(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = connect(db_path)
    try:
        row = con.execute("SELECT * FROM schedule WHERE singleton=1").fetchone()
        result = dict(row)
        result["enabled"] = bool(result["enabled"])
        result["source_ids"] = json.loads(result.pop("source_ids_json"))
        return result
    finally: con.close()


def list_inbox(state: str | None = None, limit: int = 50, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    if not 1 <= limit <= 200: raise ValueError("limit должен быть от 1 до 200")
    if state not in (None, "queued", "reviewed", "dismissed"): raise ValueError("unknown inbox state")
    con = connect(db_path)
    try:
        where = "WHERE i.state=?" if state else ""
        params = (state, limit) if state else (limit,)
        return [dict(r) for r in con.execute(f"SELECT i.id,i.source_id,i.source_kind,i.external_id,i.content_sha256,i.title,substr(i.text,1,500) AS preview,length(i.text) AS text_chars,i.published_at,i.source_url,i.metadata_json,i.state,i.collected_at,i.job_id,s.title AS source_title FROM inbox i LEFT JOIN sources s ON s.id=i.source_id {where} ORDER BY i.collected_at DESC LIMIT ?", params)]
    finally: con.close()


def get_inbox_item(item_id: str, db_path: Path = DB_PATH) -> dict[str, Any] | None:
    con = connect(db_path)
    try:
        row = con.execute("SELECT * FROM inbox WHERE id=?", (item_id,)).fetchone()
        if not row: return None
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json"))
        return item
    finally: con.close()


def update_inbox_state(item_id: str, state: str, db_path: Path = DB_PATH) -> dict[str, Any] | None:
    if state not in {"reviewed", "dismissed"}: raise ValueError("state must be reviewed or dismissed")
    con = connect(db_path)
    try:
        cur = con.execute("UPDATE inbox SET state=? WHERE id=?", (state, item_id))
        con.commit()
        if not cur.rowcount: return None
    finally: con.close()
    return get_inbox_item(item_id, db_path)


def status(db_path: Path = DB_PATH) -> dict[str, Any]:
    con = connect(db_path)
    try:
        sources = dict(con.execute("SELECT kind,count(*) FROM sources WHERE active=1 GROUP BY kind"))
        jobs = dict(con.execute("SELECT status,count(*) FROM operations_jobs GROUP BY status"))
        inbox = dict(con.execute("SELECT state,count(*) FROM inbox GROUP BY state"))
        return {"sources": sources, "jobs": jobs, "inbox": inbox, "schedule": get_schedule(db_path),
                "worker_running": bool(_worker_thread and _worker_thread.is_alive())}
    finally: con.close()


def recover_interrupted_jobs(db_path: Path = DB_PATH) -> int:
    con = connect(db_path)
    try:
        cur = con.execute("UPDATE operations_jobs SET status='interrupted',finished_at=?,error='worker stopped before recording completion' WHERE status='running'", (_now(),))
        con.commit()
        return cur.rowcount
    finally: con.close()


def _latest_timestamp(path: Path):
    from datetime import datetime as dt
    latest = None
    if not path.exists(): return None
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                value = dt.fromisoformat(json.loads(line).get("published_at", ""))
                if latest is None or value > latest: latest = value
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
    return latest


def _collect_vk(source: dict[str, Any], limit: int, job_id: str, db_path: Path = DB_PATH,
                extractor_factory=None, cleaner=None) -> dict[str, Any]:
    """Use the extractor directly; no LLM/indexer and no source truncation."""
    from backend.admin.secrets import get_secret

    if cleaner is None:
        from scraper.cleaners.text_cleaner import clean_text
        cleaner = clean_text

    if extractor_factory is None:
        from scraper.extractors.vk import VkApiExtractor
        extractor_factory = VkApiExtractor

    token = get_secret("VK_SERVICE_TOKEN") or get_secret("VK_SERVICE_TOKEN1")
    if not token: raise RuntimeError("VK_SERVICE_TOKEN is not configured")
    extractor = extractor_factory(token)
    group = extractor.resolve_group(source["url"])
    path = STORAGE_DIR / "posts" / f"posts_{source['domain']}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    latest = datetime.fromisoformat(source["last_collected_at"]) if source.get("last_collected_at") else None
    existing_ids: set[str] = set()
    if path.exists():
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    row = json.loads(line); existing_ids.add(str(row.get("post_id", "")))
                except json.JSONDecodeError: continue
    collected: list[dict[str, Any]] = []
    append_rows: list[dict[str, Any]] = []
    for raw in extractor.fetch_posts(limit, last_timestamp=latest):
        if _worker_stop.is_set(): raise InterruptedError("worker shutdown requested")
        item = dict(raw)
        raw_id = str(item.get("post_id", ""))
        external_id = raw_id
        if not external_id.startswith("wall-"):
            parsed = urlparse(str(item.get("post_url", "")))
            wall = parse_qs(parsed.query).get("w", [""])[0]
            if re.fullmatch(r"wall-?\d+_\d+", wall): external_id = wall
            else: external_id = f"wall-{abs(int(item.get('group_id', group.get('group_id', 0))))}_{raw_id}"
        already_saved = raw_id in existing_ids or external_id in existing_ids
        original = str(item.get("text_raw") or "")
        cleaned, hashtags, mentions = cleaner(original)
        item["post_id"] = raw_id
        item["source_platform"] = "vk"
        item["group_id"] = str(item.get("group_id") or group["group_id"])
        item["group_domain"] = source["domain"]
        item["group_name"] = str(item.get("group_name") or source.get("title") or source["domain"])
        item["post_url"] = str(item.get("post_url") or f"https://vk.com/wall{external_id.removeprefix('wall')}")
        item["text_raw"] = original
        item["text_clean"] = cleaned
        item["hashtags"] = hashtags
        item["mentions"] = mentions
        item.setdefault("attachments", {"photos": [], "links": [], "docs": []})
        collected.append(item)
        if not already_saved:
            append_rows.append(item)
            existing_ids.update((raw_id, external_id))
    # Append the source corpus first, then create the inbox receipt. On restart,
    # duplicate IDs are skipped while the inbox unique key remains idempotent.
    with path.open("a", encoding="utf-8") as stream:
        if append_rows and path.stat().st_size:
            with path.open("rb") as existing:
                existing.seek(-1, os.SEEK_END)
                if existing.read(1) != b"\n":
                    # A process may have died during its previous append.
                    # Isolate any incomplete tail instead of concatenating the
                    # next valid JSON object onto it.
                    stream.write("\n")
        for item in append_rows:
            stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        stream.flush(); os.fsync(stream.fileno())
    con = connect(db_path)
    try:
        latest_watermark = datetime.fromisoformat(source["last_collected_at"]) if source.get("last_collected_at") else None
        inbox_added = 0
        for item in collected:
            external_id = str(item["post_id"])
            raw = item["text_raw"]
            digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            metadata = {k: item.get(k) for k in ("group_domain", "group_id", "hashtags", "mentions", "attachments")}
            cur = con.execute("INSERT OR IGNORE INTO inbox(id,source_id,source_kind,external_id,content_sha256,title,text,published_at,source_url,metadata_json,state,collected_at,job_id) VALUES(?,?,?,?,?,?,?,?,?,?, 'queued',?,?)",
                        (uuid.uuid4().hex, source["id"], "vk", external_id, digest, item["group_name"], raw,
                         item.get("published_at"), item["post_url"], json.dumps(metadata, ensure_ascii=False), _now(), job_id))
            inbox_added += cur.rowcount
            try:
                published = datetime.fromisoformat(item["published_at"])
                if latest_watermark is None or published > latest_watermark: latest_watermark = published
            except (TypeError, ValueError):
                pass
        if latest_watermark:
            con.execute("UPDATE sources SET last_collected_at=? WHERE id=?", (latest_watermark.isoformat(), source["id"]))
        con.commit()
    finally: con.close()
    return {"fetched": len(append_rows), "parsed": len(collected), "inbox_added": inbox_added,
            "source_path": path.name, "latest_published_at": latest_watermark.isoformat() if latest_watermark else ""}


def _collect_vk_post(source: dict[str, Any], job_id: str, db_path: Path = DB_PATH,
                     extractor_factory=None, cleaner=None) -> dict[str, Any]:
    from backend.admin.secrets import get_secret
    from scraper.extractors.vk_parsers import parse_attachments, post_timestamp
    if extractor_factory is None:
        from scraper.extractors.vk import VkApiExtractor
        extractor_factory = VkApiExtractor
    if cleaner is None:
        from scraper.cleaners.text_cleaner import clean_text
        cleaner = clean_text
    token = get_secret("VK_SERVICE_TOKEN") or get_secret("VK_SERVICE_TOKEN1")
    if not token: raise RuntimeError("VK_SERVICE_TOKEN is not configured")
    extractor = extractor_factory(token)
    wall_match = re.fullmatch(r"wall(-?\d+)_(\d+)", source["domain"])
    if not wall_match: raise ValueError("Stored VK permalink is invalid")
    owner_id, post_id = int(wall_match.group(1)), int(wall_match.group(2))
    response = extractor.api.wall.getById(posts=f"{owner_id}_{post_id}")
    posts = response.get("items", []) if isinstance(response, dict) else response
    if not posts: raise RuntimeError("VK post was not found or is unavailable")
    post = posts[0]
    text_raw = str(post.get("text") or "")
    text_clean, hashtags, mentions = cleaner(text_raw)
    photos, links, docs = parse_attachments(post.get("attachments") or [])
    published = post_timestamp(post).isoformat()
    raw_id = str(post.get("id", post_id))
    metadata = {"owner_id": owner_id, "post_id": raw_id, "source_kind": "vk_post",
                "attachments": {"photos": photos, "links": links, "docs": docs},
                "hashtags": hashtags, "mentions": mentions}
    digest = hashlib.sha256(text_raw.encode("utf-8")).hexdigest()
    con = connect(db_path)
    try:
        cur = con.execute("INSERT OR IGNORE INTO inbox(id,source_id,source_kind,external_id,content_sha256,title,text,published_at,source_url,metadata_json,state,collected_at,job_id) VALUES(?,?,?,?,?,?,?,?,?,?, 'queued',?,?)",
                          (uuid.uuid4().hex, source["id"], "vk_post", source["domain"], digest,
                           source["title"], text_raw, published, source["url"],
                           json.dumps(metadata, ensure_ascii=False), _now(), job_id))
        con.commit()
        return {"fetched": 1, "parsed": 1, "inbox_added": cur.rowcount,
                "latest_published_at": published}
    finally:
        con.close()


def _run_job(job_id: str, db_path: Path = DB_PATH) -> None:
    con = connect(db_path)
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT j.*,s.domain,s.url,s.title,s.active,s.last_collected_at FROM operations_jobs j JOIN sources s ON s.id=j.source_id WHERE j.id=?", (job_id,)).fetchone()
        if not row or row["status"] != "queued":
            con.rollback()
            return
        claimed = con.execute("UPDATE operations_jobs SET status='running',started_at=?,attempts=attempts+1,error='' WHERE id=? AND status='queued'", (_now(), job_id))
        if claimed.rowcount != 1:
            con.rollback()
            return
        con.commit()
        job = dict(row)
        source = {"id": job["source_id"], "kind": row["kind"], "domain": row["domain"],
                  "url": row["url"], "title": row["title"], "active": row["active"],
                  "last_collected_at": row["last_collected_at"]}
    finally: con.close()
    try:
        if job["kind"] == "vk_post_fetch":
            result = _collect_vk_post(source, job_id, db_path)
        else:
            result = _collect_vk(source, int(json.loads(job["result_json"]).get("limit", 0)), job_id, db_path)
        con = connect(db_path)
        try:
            con.execute("UPDATE operations_jobs SET status='succeeded',finished_at=?,result_json=? WHERE id=?",
                        (_now(), json.dumps({**json.loads(job["result_json"]), **result}, ensure_ascii=False), job_id)); con.commit()
        finally: con.close()
    except InterruptedError as exc:
        con = connect(db_path)
        try: con.execute("UPDATE operations_jobs SET status='interrupted',finished_at=?,error=? WHERE id=?", (_now(), str(exc), job_id)); con.commit()
        finally: con.close()
    except Exception as exc:
        detail = str(exc)
        try:
            from backend.admin.secrets import get_secret
            for secret_name in ("VK_SERVICE_TOKEN", "VK_SERVICE_TOKEN1"):
                secret = get_secret(secret_name)
                if secret: detail = detail.replace(secret, "[REDACTED]")
        except Exception:
            pass
        detail = re.sub(r"(?i)(access_token|token)=([^&\s]+)", r"\1=[REDACTED]", detail)
        con = connect(db_path)
        try:
            con.execute("UPDATE operations_jobs SET status='failed',finished_at=?,error=? WHERE id=?", (_now(), f"{type(exc).__name__}: {detail}"[:1000], job_id)); con.commit()
        finally: con.close()


def _schedule_due(db_path: Path = DB_PATH) -> None:
    now = datetime.now(ZoneInfo(TZ_NAME))
    con = connect(db_path)
    try:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM schedule WHERE singleton=1").fetchone()
        if not row or not row["enabled"] or now.strftime("%H:%M") < row["local_time"] or row["last_run_date"] == now.date().isoformat():
            con.rollback(); return
        source_ids = json.loads(row["source_ids_json"])
        con.execute("UPDATE schedule SET last_run_date=? WHERE singleton=1", (now.date().isoformat(),))
        for source_id in source_ids:
            source = con.execute("SELECT id FROM sources WHERE id=? AND kind='vk' AND active=1", (source_id,)).fetchone()
            if source:
                con.execute("INSERT INTO operations_jobs(id,kind,source_id,status,created_at,result_json,scheduled_for) VALUES(?, 'vk_fetch', ?, 'queued', ?, ?, ?)",
                            (uuid.uuid4().hex, source_id, _now(), json.dumps({"limit": 0, "trigger": "daily_schedule"}), now.isoformat()))
        con.commit()
    except Exception:
        con.rollback(); raise
    finally: con.close()


def _worker_main(db_path: Path) -> None:
    lock_path = Path(str(db_path) + ".worker.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_stream = lock_path.open("a+")
    try:
        try:
            fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            import logging
            logging.getLogger("admin_operations").warning("operations worker already owned by another process")
            return
        recover_interrupted_jobs(db_path)
        _worker_owned_loop(db_path)
    finally:
        lock_stream.close()


def _worker_owned_loop(db_path: Path) -> None:
    while not _worker_stop.is_set():
        try:
            _schedule_due(db_path)
            con = connect(db_path)
            try:
                row = con.execute("SELECT id FROM operations_jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            finally: con.close()
            if row:
                _run_job(row["id"], db_path)
                continue
        except Exception:
            # Record worker-loop failure at process log level, then keep the
            # scheduler alive; job-specific failures live on the job row.
            import logging
            logging.getLogger("admin_operations").exception("operations worker iteration failed")
        _worker_wake.wait(15)
        _worker_wake.clear()


def start_operations_worker(db_path: Path = DB_PATH) -> None:
    global _worker_thread
    with _worker_lock:
        if _worker_thread and _worker_thread.is_alive(): return
        connect(db_path).close()
        _worker_stop.clear(); _worker_wake.set()
        _worker_thread = threading.Thread(target=_worker_main, args=(db_path,), name="tesla-operations", daemon=True)
        _worker_thread.start()


def stop_operations_worker(timeout: float = 10.0) -> None:
    _worker_stop.set(); _worker_wake.set()
    thread = _worker_thread
    if thread and thread.is_alive(): thread.join(timeout=max(0.0, timeout))
