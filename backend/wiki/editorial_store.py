"""Private editorial drafts, immutable revisions and article discussions.

Published Markdown remains the Wiki's source of truth. Drafts and discussions
live below _editorial and never enter the public reader or answer context.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import uuid

SLUG = re.compile(r"^[a-z0-9][a-z0-9_]*(?:/[a-z0-9][a-z0-9_]*)*$")
LINK = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
URL = re.compile(r"\[[^\]]*\]\(((?:https?://|/api/v1/wiki/source\?)[^)]+)\)")
TITLE = re.compile(r"(?m)^#\s+(.+?)\s*$")
STATUSES = {"waiting_editor", "waiting_curator", "resolved"}
CATEGORIES = {"curator_question", "source_conflict", "editorial_note"}
_THREAD_LOCK = threading.RLock()


class EditorialConflict(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    temp: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".editorial-", delete=False) as stream:
            temp = stream.name
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)


class EditorialStore:
    def __init__(self, wiki: Path):
        self.wiki = wiki.resolve()
        self.private = self.wiki / "_editorial"
        self.private.mkdir(parents=True, exist_ok=True)
        if self.private.is_symlink() or not self.private.resolve().is_relative_to(self.wiki):
            raise ValueError("Редакторское хранилище находится вне вики")
        os.chmod(self.private, 0o700)
        self.db = self.private / "editorial.sqlite"
        if self.db.exists() and not self.db.resolve().is_relative_to(self.private):
            raise ValueError("Недопустимый путь редакторской базы")

    @contextmanager
    def _locked(self):
        # A process-wide thread lock plus flock also serializes different API
        # processes. The compiler stays paused; external changes are detected
        # by comparing the current file hash before every publication.
        with _THREAD_LOCK, (self.private / ".cabinet.lock").open("a") as lock:
            os.chmod(self.private / ".cabinet.lock", 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            conn = sqlite3.connect(self.db, timeout=20)
            os.chmod(self.db, 0o600)
            conn.row_factory = sqlite3.Row
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS versions (
                        id TEXT PRIMARY KEY, slug TEXT NOT NULL, markdown TEXT NOT NULL,
                        sha256 TEXT NOT NULL, created_at TEXT NOT NULL, actor TEXT NOT NULL,
                        reason TEXT NOT NULL, kind TEXT NOT NULL, applied INTEGER NOT NULL DEFAULT 1
                    );
                    CREATE INDEX IF NOT EXISTS versions_page ON versions(slug, created_at);
                    CREATE TABLE IF NOT EXISTS drafts (
                        slug TEXT PRIMARY KEY, markdown TEXT NOT NULL, base_revision TEXT NOT NULL,
                        revision TEXT NOT NULL, updated_at TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS discussions (
                        id TEXT PRIMARY KEY, page TEXT NOT NULL, title TEXT NOT NULL,
                        original_text TEXT NOT NULL, category TEXT NOT NULL, status TEXT NOT NULL,
                        owner TEXT NOT NULL DEFAULT '', resolution TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, legacy_json TEXT
                    );
                    CREATE TABLE IF NOT EXISTS comments (
                        id TEXT PRIMARY KEY, discussion_id TEXT NOT NULL,
                        text TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL
                    );
                """)
                self._import_issues(conn)
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
            finally:
                conn.close()
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _path(self, slug: str) -> Path:
        if len(slug) > 200 or not SLUG.fullmatch(slug) or slug.rsplit("/", 1)[-1] in {"log", "agents"}:
            raise ValueError("Недопустимый адрес статьи")
        candidate = self.wiki / (slug + ".md")
        if not candidate.resolve().is_relative_to(self.wiki):
            raise ValueError("Статья находится вне вики")
        return candidate

    def _canonical(self, slug: str) -> str:
        seen = set()
        while True:
            if slug in seen or len(seen) >= 8:
                raise ValueError("Циклическое перенаправление статьи")
            seen.add(slug)
            path = self._path(slug)
            if not path.exists():
                return slug
            text = path.read_text(encoding="utf-8")
            match = re.search(r"(?m)^redirect_to:\s*([a-z0-9_/]+)\s*$", text)
            if not match:
                return slug
            slug = match[1]

    def _current(self, slug: str) -> tuple[str, str]:
        path = self._path(slug)
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        return text, _hash(text) if path.exists() else ""

    def _baseline(self, conn: sqlite3.Connection, slug: str, text: str, revision: str) -> None:
        if not revision:
            return
        conn.execute("UPDATE versions SET applied=1 WHERE slug=? AND sha256=? AND applied=0", (slug, revision))
        row = conn.execute("SELECT sha256 FROM versions WHERE slug=? AND applied=1 ORDER BY created_at DESC, rowid DESC LIMIT 1", (slug,)).fetchone()
        if row is None or row["sha256"] != revision:
            # Also captures a manual file change made outside this cabinet.
            conn.execute("INSERT INTO versions VALUES (?,?,?,?,?,?,?,?,1)",
                         (uuid.uuid4().hex, slug, text, revision, _now(), "Архив", "Версия до редакторского изменения", "snapshot"))

    def _meta(self, slug: str, text: str) -> dict:
        title = TITLE.search(text)
        kind = re.search(r"(?m)^kind:\s*([^\n]+)", text)
        updated = re.search(r"(?m)^updated_at:\s*([^\n]+)", text)
        status = re.search(r"(?m)^status:\s*([^\n]+)", text)
        return {"slug": slug, "title": title[1] if title else slug,
                "kind": kind[1].strip(" '\"") if kind else slug.split("/")[0],
                "updated_at": updated[1].strip(" '\"") if updated else "",
                "status": status[1].strip(" '\"") if status else "ok"}

    def articles(self, query: str = "") -> list[dict]:
        rows: dict[str, dict] = {}
        with self._locked() as conn:
            drafts = {r["slug"]: dict(r) for r in conn.execute("SELECT * FROM drafts")}
            for path in self.wiki.rglob("*.md"):
                relative = path.relative_to(self.wiki)
                if any(part.startswith(("_", ".")) for part in relative.parts) or path.name in {"AGENTS.md", "log.md"}:
                    continue
                slug = relative.with_suffix("").as_posix()
                if not SLUG.fullmatch(slug) or not path.resolve().is_relative_to(self.wiki):
                    continue
                text = path.read_text(encoding="utf-8")
                if re.search(r"(?m)^redirect_to:", text):
                    continue
                revision = _hash(text)
                # Recover a publish that replaced the file before its SQLite
                # applied flag was committed.
                conn.execute("UPDATE versions SET applied=1 WHERE slug=? AND sha256=? AND applied=0", (slug, revision))
                rows[slug] = {**self._meta(slug, text), "revision": revision, "has_draft": slug in drafts}
            pending: dict[str, list[str]] = {}
            for item in conn.execute("SELECT id,slug FROM versions WHERE applied=0 ORDER BY created_at DESC,rowid DESC"):
                pending.setdefault(item["slug"], []).append(item["id"])
            for slug, draft in drafts.items():
                if slug not in rows:
                    rows[slug] = {**self._meta(slug, draft["markdown"]), "status": "draft", "revision": "", "has_draft": True, "updated_at": draft["updated_at"]}
            for slug, versions in pending.items():
                if slug in rows:
                    rows[slug]["has_pending"] = True
                    rows[slug]["pending_version_ids"] = versions
                    continue
                item = conn.execute("SELECT markdown,created_at FROM versions WHERE id=? AND applied=0", (versions[0],)).fetchone()
                rows[slug] = {**self._meta(slug, item["markdown"]), "status": "pending",
                              "revision": "", "has_draft": False, "has_pending": True,
                              "pending_version_ids": versions, "updated_at": item["created_at"]}
        terms = query.casefold().split()
        return sorted((r for r in rows.values() if all(t in (r["title"] + " " + r["slug"]).casefold() for t in terms)), key=lambda r: r["title"].casefold())

    def article(self, slug: str) -> dict:
        slug = self._canonical(slug)
        with self._locked() as conn:
            text, revision = self._current(slug)
            draft = conn.execute("SELECT * FROM drafts WHERE slug=?", (slug,)).fetchone()
            pending_rows = conn.execute("SELECT id,created_at,actor,reason,sha256,kind,markdown FROM versions WHERE slug=? AND applied=0 ORDER BY created_at DESC,rowid DESC", (slug,)).fetchall()
            if not revision and not draft and not pending_rows:
                raise KeyError("Статья не найдена")
            self._baseline(conn, slug, text, revision)
            draft_data = dict(draft) if draft else None
            # _baseline may have promoted a candidate matching the file.
            pending_rows = conn.execute("SELECT id,created_at,actor,reason,sha256,kind,markdown FROM versions WHERE slug=? AND applied=0 ORDER BY created_at DESC,rowid DESC", (slug,)).fetchall()
            pending_versions = [{key: row[key] for key in ("id", "created_at", "actor", "reason", "sha256", "kind")} | {"publication_state": "pending", "is_current": False} for row in pending_rows]
        from backend.wiki.sources import source_details
        urls = list(dict.fromkeys(URL.findall(text)))
        fallback = text or (draft_data["markdown"] if draft_data else "")
        if not fallback and pending_rows:
            fallback = pending_rows[0]["markdown"]
        return {**self._meta(slug, fallback), "markdown": text,
                "revision": revision, "draft": draft_data, "pending_versions": pending_versions,
                "sources": source_details(urls, self.wiki)}

    def _validate(self, slug: str, markdown: str, old: str = "") -> None:
        if not isinstance(markdown, str) or not markdown.strip() or len(markdown.encode("utf-8")) > 2_000_000 or "\x00" in markdown:
            raise ValueError("Пустая или слишком большая статья")
        if not TITLE.search(markdown):
            raise ValueError("Укажите заголовок статьи: # Название")
        if markdown.startswith("---"):
            front = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", markdown, re.S)
            if not front:
                raise ValueError("Незакрытый блок метаданных статьи")
            declared = re.search(r"(?m)^slug:\s*['\"]?([^\s'\"]+)", front[1])
            if declared and declared[1] != slug:
                raise ValueError("Адрес в метаданных не совпадает с адресом статьи")
            if re.search(r"(?m)^redirect_to:", front[1]):
                raise ValueError("Перенаправление нельзя публиковать как статью")
        old_links = set(LINK.findall(old))
        missing = []
        for link in set(LINK.findall(markdown)):
            target = link.split("#", 1)[0]
            if target == slug:
                continue
            try:
                exists = self._path(target).is_file()
            except ValueError:
                exists = False
            if not exists and link not in old_links:
                missing.append(target)
        if missing:
            raise ValueError("Нет связанных статей: " + ", ".join(sorted(missing)))

    def save_draft(self, slug: str, markdown: str, expected_revision: str,
                   expected_draft_revision: str | None, actor: str = "Редактор", reason: str = "") -> dict:
        slug = self._canonical(slug)
        with self._locked() as conn:
            current, revision = self._current(slug)
            if revision != expected_revision:
                raise EditorialConflict("Статья изменилась. Обновите её перед сохранением.")
            existing = conn.execute("SELECT * FROM drafts WHERE slug=?", (slug,)).fetchone()
            if (existing["revision"] if existing else None) != expected_draft_revision:
                raise EditorialConflict("Черновик уже изменён. Откройте его заново.")
            if not isinstance(markdown, str) or not markdown.strip() or len(markdown.encode("utf-8")) > 2_000_000 or "\x00" in markdown:
                raise ValueError("Пустой или слишком большой черновик")
            self._baseline(conn, slug, current, revision)
            result = {"slug": slug, "markdown": markdown, "base_revision": revision,
                      "revision": uuid.uuid4().hex, "updated_at": _now(), "actor": actor, "reason": reason}
            conn.execute("INSERT OR REPLACE INTO drafts VALUES (?,?,?,?,?,?,?)", tuple(result.values()))
            return result

    def publish(self, slug: str, markdown: str, expected_revision: str, reason: str,
                actor: str = "Редактор", kind: str = "publication") -> dict:
        slug = self._canonical(slug)
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Укажите причину публикации или восстановления")
        with self._locked() as conn:
            old, revision = self._current(slug)
            if revision != expected_revision:
                raise EditorialConflict("Статья изменилась. Сравните изменения перед публикацией.")
            self._validate(slug, markdown, old)
            self._baseline(conn, slug, old, revision)
            submitted = markdown
            # Preserve frontmatter when a human edits only the readable body.
            if kind != "restore" and old.startswith("---\n") and not markdown.startswith("---"):
                front = re.match(r"\A---\n.*?\n---\n", old, re.S)
                if front:
                    markdown = front[0] + "\n" + markdown
            if kind != "restore":
                if not markdown.startswith("---\n"):
                    title = TITLE.search(markdown)[1]
                    markdown = ("---\nslug: " + slug + "\nkind: " + slug.split("/")[0]
                                + "\nsource_model: manual_editorial\nstatus: ok\ntitle: "
                                + json.dumps(title, ensure_ascii=False) + "\ntags: []\n---\n\n" + markdown)
                front = re.match(r"\A---\n(.*?)\n---\n", markdown, re.S)
                if front:
                    fields = front[1]
                    for key, value in (("updated_at", _now()), ("source_model", "manual_editorial")):
                        if re.search(rf"(?m)^{key}:", fields):
                            fields = re.sub(rf"(?m)^{key}:.*$", key + ": " + value, fields)
                        else:
                            fields += "\n" + key + ": " + value
                    markdown = "---\n" + fields + "\n---\n" + markdown[front.end():]
            markdown = markdown.rstrip() + "\n"
            new_revision = _hash(markdown)
            version_id = uuid.uuid4().hex
            conn.execute("INSERT INTO versions VALUES (?,?,?,?,?,?,?,?,0)",
                         (version_id, slug, markdown, new_revision, _now(), actor, reason.strip(), kind))
            conn.commit()  # Both the old page and the intended new page survive a failed write.
            if self._current(slug)[1] != revision:
                raise EditorialConflict("Файл изменён другим процессом перед публикацией")
            _atomic_write(self._path(slug), markdown)
            conn.execute("UPDATE versions SET applied=1 WHERE id=?", (version_id,))
            # Never discard a different draft created by another editor.
            draft = conn.execute("SELECT markdown, base_revision FROM drafts WHERE slug=?", (slug,)).fetchone()
            if draft and draft["markdown"].rstrip() == submitted.rstrip() and draft["base_revision"] == revision:
                conn.execute("DELETE FROM drafts WHERE slug=?", (slug,))
            return {"ok": True, "slug": slug, "revision": new_revision, "version_id": version_id}

    def history(self, slug: str) -> list[dict]:
        slug = self._canonical(slug)
        with self._locked() as conn:
            text, revision = self._current(slug)
            self._baseline(conn, slug, text, revision)
            # Recover a file written just before an API process was interrupted.
            conn.execute("UPDATE versions SET applied=1 WHERE slug=? AND sha256=?", (slug, revision))
            rows = conn.execute("SELECT id,created_at,actor,reason,sha256,kind,applied FROM versions WHERE slug=? ORDER BY created_at DESC,rowid DESC", (slug,)).fetchall()
            current_id = next((r["id"] for r in rows if r["applied"] and r["sha256"] == revision), None)
            return [{**dict(r), "publication_state": "published" if r["applied"] else "pending",
                     "is_current": bool(r["applied"] and r["id"] == current_id)} for r in rows]

    def version(self, slug: str, version_id: str) -> dict:
        slug = self._canonical(slug)
        with self._locked() as conn:
            row = conn.execute("SELECT * FROM versions WHERE id=? AND slug=?", (version_id, slug)).fetchone()
            if row is None:
                raise KeyError("Версия не найдена")
            current = conn.execute("SELECT id FROM versions WHERE slug=? AND sha256=? AND applied=1 ORDER BY created_at DESC,rowid DESC LIMIT 1", (slug, self._current(slug)[1])).fetchone()
            return {**dict(row), "publication_state": "published" if row["applied"] else "pending",
                    "is_current": bool(row["applied"] and current and current["id"] == version_id)}

    def restore(self, slug: str, version_id: str, expected_revision: str, reason: str, actor: str) -> dict:
        old = self.version(slug, version_id)
        markdown = old["markdown"]
        canonical = self._canonical(slug)
        if old["kind"] == "archive" and markdown.startswith("---\n"):
            # Archives may predate consolidation of aliases. Preserve the
            # original version in history while restoring to today's address.
            front = re.match(r"\A---\n(.*?)\n---\n", markdown, re.S)
            if front:
                fields = re.sub(r"(?m)^slug:.*$", "slug: " + canonical, front[1])
                markdown = "---\n" + fields + "\n---\n" + markdown[front.end():]
        return self.publish(canonical, markdown, expected_revision, reason, actor, "restore")

    def _import_issues(self, conn: sqlite3.Connection) -> None:
        path = self.private / "issues.json"
        if not path.exists():
            return
        issues = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(issues, list):
            raise ValueError("Не удалось прочитать сохранённые дискуссии")
        for item in issues:
            if not isinstance(item, dict) or not item.get("id") or not item.get("page"):
                continue
            text = str(item.get("original_text", ""))
            resolution = item.get("resolution") or ""
            if not isinstance(resolution, str):
                resolution = json.dumps(resolution, ensure_ascii=False)
            status = "resolved" if item.get("status") in {"resolved", "closed", "confirmed", "dismissed"} else "waiting_editor"
            category = "editorial_note"
            if re.search(r"вопрос хранителю|уточнить у хранителя|уточнить у Альфреда", text, re.I):
                category = "curator_question"
                if status != "resolved":
                    status = "waiting_curator"
            elif re.search(r"противореч|расхожд|разнятся", text, re.I):
                category = "source_conflict"
            created = item.get("created_at") or item.get("reviewed_at") or _now()
            title = re.sub(r"^[\s#*\d.\-]+", "", text.splitlines()[0] if text else "Уточнение статьи")[:150]
            conn.execute("INSERT OR IGNORE INTO discussions VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                str(item["id"]), str(item["page"]), title, text, category, status, "", resolution,
                created, item.get("reviewed_at") or created, json.dumps(item, ensure_ascii=False)))

    def _discussion(self, conn: sqlite3.Connection, discussion_id: str) -> dict:
        row = conn.execute("SELECT * FROM discussions WHERE id=?", (discussion_id,)).fetchone()
        if row is None:
            raise KeyError("Дискуссия не найдена")
        result = dict(row)
        result.pop("legacy_json", None)
        result["comments"] = [dict(r) for r in conn.execute("SELECT id,text,actor,created_at FROM comments WHERE discussion_id=? ORDER BY created_at,rowid", (discussion_id,))]
        return result

    def discussions(self, slug: str = "", status: str = "") -> list[dict]:
        if status and status not in STATUSES:
            raise ValueError("Неизвестное состояние дискуссии")
        with self._locked() as conn:
            rows = conn.execute("SELECT id FROM discussions WHERE (?='' OR page=?) AND (?='' OR status=?) ORDER BY updated_at DESC,rowid DESC", (slug, slug, status, status)).fetchall()
            return [self._discussion(conn, r["id"]) for r in rows]

    def add_discussion(self, page: str, title: str, text: str, category: str = "editorial_note", owner: str = "", actor: str = "Редактор") -> dict:
        page = self._canonical(page)
        if category not in CATEGORIES or not title.strip() or not text.strip() or len(text) > 50000 or len(title) > 200:
            raise ValueError("Укажите тему, текст и тип дискуссии")
        with self._locked() as conn:
            if not self._path(page).exists() and not conn.execute("SELECT slug FROM drafts WHERE slug=?", (page,)).fetchone():
                raise KeyError("Связанная статья не найдена")
            stamp, ident = _now(), uuid.uuid4().hex
            conn.execute("INSERT INTO discussions VALUES (?,?,?,?,?,?,?,?,?,?,NULL)",
                         (ident, page, title.strip(), text.strip(), category, "waiting_curator" if category == "curator_question" else "waiting_editor", owner[:150], "", stamp, stamp))
            conn.execute("INSERT INTO comments VALUES (?,?,?,?,?)", (uuid.uuid4().hex, ident, text.strip(), actor, stamp))
            return self._discussion(conn, ident)

    def update_discussion(self, ident: str, changes: dict, actor: str = "Редактор") -> dict:
        with self._locked() as conn:
            current = self._discussion(conn, ident)
            expected = changes.get("expected_updated_at")
            if expected is not None and expected != current["updated_at"]:
                raise EditorialConflict("Дискуссия уже изменена. Обновите её.")
            status = changes.get("status", current["status"])
            category = changes.get("category", current["category"])
            resolution = changes.get("resolution", current["resolution"])
            owner = changes.get("owner", current["owner"])
            if status not in STATUSES or category not in CATEGORIES or not isinstance(resolution, str) or not isinstance(owner, str) or len(resolution) > 50000:
                raise ValueError("Некорректное решение или состояние дискуссии")
            if status == "resolved" and not resolution.strip():
                raise ValueError("Запишите основание решения перед закрытием дискуссии")
            stamp = _now()
            conn.execute("UPDATE discussions SET status=?,category=?,owner=?,resolution=?,updated_at=? WHERE id=?", (status, category, owner[:150], resolution, stamp, ident))
            if resolution != current["resolution"]:
                conn.execute("INSERT INTO comments VALUES (?,?,?,?,?)", (uuid.uuid4().hex, ident, resolution, actor, stamp))
            return self._discussion(conn, ident)

    def comment(self, ident: str, text: str, actor: str) -> dict:
        if not isinstance(text, str) or not text.strip() or len(text) > 50000:
            raise ValueError("Введите текст замечания")
        with self._locked() as conn:
            self._discussion(conn, ident)
            stamp = _now()
            conn.execute("INSERT INTO comments VALUES (?,?,?,?,?)", (uuid.uuid4().hex, ident, text.strip(), actor, stamp))
            conn.execute("UPDATE discussions SET updated_at=? WHERE id=?", (stamp, ident))
            return self._discussion(conn, ident)

    def source_excerpt(self, item: dict, line_start: int, line_end: int, actor: str) -> dict:
        """Explicitly publish only the selected evidence, never a whole upload."""
        from backend.wiki.archive import DOCUMENT_ID, read_records, source_url
        if item.get("source_kind") != "document":
            raise ValueError("Для публикации VK используйте её исходную ссылку")
        text = str(item.get("text") or "")
        lines = text.splitlines()
        if not 1 <= line_start <= line_end <= len(lines) or line_end - line_start >= 500:
            raise ValueError("Выберите существующий диапазон, не более 500 строк")
        excerpt = "\n".join(lines[line_start - 1:line_end])
        if not excerpt.strip() or len(excerpt) > 100000:
            raise ValueError("Фрагмент пуст или слишком велик")
        doc_id = str(item.get("external_id") or "").removeprefix("document:")
        ref = f"document:{doc_id}:{_hash(text)[:16]}:L{line_start}-L{line_end}"
        if not DOCUMENT_ID.fullmatch(ref):
            raise ValueError("Некорректный идентификатор документа")
        title = str(item.get("title") or item.get("source_title") or "Загруженный документ")
        title += f", строки {line_start}–{line_end}"
        url = source_url(ref)
        with self._locked():
            records = read_records(self.wiki)
            record = {"url": url, "text": excerpt, "title": title, "group_name": "Загруженный документ",
                      "published_at": item.get("published_at") or "", "source_segments": [],
                      "source_kind": "document", "document_id": doc_id, "text_sha256": _hash(text),
                      "line_start": line_start, "line_end": line_end, "published_by": actor, "registered_at": _now()}
            if ref not in records:
                records[ref] = record
                _atomic_write(self.wiki / "_source_records.json", json.dumps(records, ensure_ascii=False, indent=2) + "\n")
        label = re.sub(r"[\[\]\\\r\n]", " ", title)
        return {"reference": ref, "url": url, "title": title, "markdown_citation": f"[Источник: {label}]({url})"}
