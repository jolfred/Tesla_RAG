"""Import archived Wiki Markdown into private editorial history without extraction."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path, PurePosixPath
import tarfile
from typing import Iterable
import uuid

from backend.wiki.editorial_store import EditorialStore, SLUG

MAX_ARTICLE_BYTES = 2_000_000
_SKIP_NAMES = {"agents.md", "log.md"}


def _member_slug(name: str) -> tuple[str | None, str]:
    """Normalize accepted archive prefixes and reject unsafe/private members."""
    path = PurePosixPath(name)
    parts = list(path.parts)
    if path.is_absolute() or any(part in {"..", ""} for part in parts):
        return None, "unsafe_path"
    parts = [part for part in parts if part not in {".", ""}]
    if not parts:
        return None, "unsafe_path"
    # Known archive layouts: `wiki/...`, `storage/wiki/...`, or article paths.
    if parts[:2] == ["storage", "wiki"]:
        parts = parts[2:]
    elif parts[0] == "wiki":
        parts = parts[1:]
    if not parts or any(part.startswith(("_", ".")) for part in parts):
        return None, "private_path"
    if parts[-1].casefold() in _SKIP_NAMES:
        return None, "service_file"
    if len(parts) == 1 and parts[0] in {"AGENTS.md", "log.md"}:
        return None, "service_file"
    if not parts[-1].endswith(".md"):
        return None, "not_markdown"
    slug = "/".join(parts)[:-3]
    if not SLUG.fullmatch(slug):
        return None, "invalid_slug"
    return slug, "ok"


def _version_id(archive_name: str, member_name: str, payload: bytes) -> str:
    digest = hashlib.sha256()
    for part in (archive_name.encode("utf-8"), member_name.encode("utf-8"), payload):
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()


def import_snapshots(wiki: Path, archives: Iterable[Path | str]) -> dict:
    """Import historical page versions from tar archives, never extracting them.

    Only members resolving to a currently existing canonical page are recorded.
    Published Markdown and the legacy issues ledger are read-only in this flow.
    Repeated imports are idempotent by archive path, member name and bytes.
    """
    store = EditorialStore(Path(wiki))
    archive_paths = [Path(value).resolve() for value in archives]
    report = {
        "archives": 0, "members": 0, "imported": 0, "duplicates": 0,
        "baselines": 0, "skipped": {}, "by_archive": [],
    }

    with store._locked() as conn:
        for archive in archive_paths:
            stat = archive.stat()
            archived_at = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec="microseconds")
            per = {"archive": str(archive), "imported": 0, "duplicates": 0, "skipped": {}}
            report["archives"] += 1
            with tarfile.open(archive, mode="r:*") as tar:
                for member in tar:
                    if not member.isfile():
                        continue
                    report["members"] += 1
                    slug, reason = _member_slug(member.name)
                    if reason != "ok":
                        report["skipped"][reason] = report["skipped"].get(reason, 0) + 1
                        per["skipped"][reason] = per["skipped"].get(reason, 0) + 1
                        continue
                    if member.size > MAX_ARTICLE_BYTES:
                        reason = "too_large"
                        report["skipped"][reason] = report["skipped"].get(reason, 0) + 1
                        per["skipped"][reason] = per["skipped"].get(reason, 0) + 1
                        continue
                    canonical = store._canonical(slug)
                    current_path = store._path(canonical)
                    if not current_path.is_file():
                        reason = "no_current_canonical_page"
                        report["skipped"][reason] = report["skipped"].get(reason, 0) + 1
                        per["skipped"][reason] = per["skipped"].get(reason, 0) + 1
                        continue
                    stream = tar.extractfile(member)
                    if stream is None:
                        reason = "unreadable_member"
                        report["skipped"][reason] = report["skipped"].get(reason, 0) + 1
                        per["skipped"][reason] = per["skipped"].get(reason, 0) + 1
                        continue
                    payload = stream.read(MAX_ARTICLE_BYTES + 1)
                    if len(payload) > MAX_ARTICLE_BYTES:
                        reason = "too_large"
                        report["skipped"][reason] = report["skipped"].get(reason, 0) + 1
                        per["skipped"][reason] = per["skipped"].get(reason, 0) + 1
                        continue
                    try:
                        markdown = payload.decode("utf-8")
                    except UnicodeDecodeError:
                        reason = "invalid_utf8"
                        report["skipped"][reason] = report["skipped"].get(reason, 0) + 1
                        per["skipped"][reason] = per["skipped"].get(reason, 0) + 1
                        continue
                    version_id = _version_id(str(archive), member.name, payload)
                    reason_text = f"Импорт исходной версии {slug} из архива {archive.name}; участник {member.name}"
                    cursor = conn.execute(
                        "INSERT OR IGNORE INTO versions(id,slug,markdown,sha256,created_at,actor,reason,kind,applied) "
                        "VALUES(?,?,?,?,?,?,?,?,1)",
                        (version_id, canonical, markdown, hashlib.sha256(payload).hexdigest(), archived_at,
                         "Архив", reason_text, "archive"),
                    )
                    if cursor.rowcount:
                        report["imported"] += 1
                        per["imported"] += 1
                    else:
                        report["duplicates"] += 1
                        per["duplicates"] += 1
            report["by_archive"].append(per)

        # Keep the currently published state recoverable as the latest known
        # baseline whenever no identical applied snapshot already exists.
        pages = conn.execute("SELECT DISTINCT slug FROM versions WHERE applied=1").fetchall()
        for row in pages:
            slug = row["slug"]
            path = store._path(slug)
            if not path.is_file():
                continue
            text, revision = store._current(slug)
            present = conn.execute("SELECT 1 FROM versions WHERE slug=? AND sha256=? AND applied=1 LIMIT 1", (slug, revision)).fetchone()
            if not present:
                before = conn.total_changes
                store._baseline(conn, slug, text, revision)
                if conn.total_changes > before:
                    report["baselines"] += 1
    return report
