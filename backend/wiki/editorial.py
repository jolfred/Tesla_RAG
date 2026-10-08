"""Keep internal editorial notes out of both public pages and answer context."""
from __future__ import annotations

import re
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

_COMMENTS = re.compile(r"<!--[\s\S]*?-->")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_PRIVATE = {
    "противоречия и дискуссии",
    "дискуссии и расхождения",
    "источники данных",
    "редакторские заметки",
}


def public_markdown(text: str) -> str:
    """Preserve the source file; omit private sections including subheadings."""
    lines: list[str] = []
    hidden_level: int | None = None
    for line in _COMMENTS.sub("", text).splitlines():
        heading = _HEADING.match(line)
        if heading:
            level = len(heading[1])
            if hidden_level is not None and level <= hidden_level:
                hidden_level = None
            if hidden_level is None and heading[2].strip().casefold() in _PRIVATE:
                hidden_level = level
        if hidden_level is None:
            lines.append(line)
    return "\n".join(lines).strip() + "\n"


def discussion_sections(text: str) -> list[str]:
    """Extract evidence retained in private discussion sections."""
    blocks: list[str] = []
    current: list[str] | None = None
    level = 0
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading and current is not None and len(heading[1]) <= level:
            blocks.append("\n".join(current).strip())
            current = None
        if heading and heading[2].strip().casefold() in _PRIVATE - {"источники данных", "редакторские заметки"}:
            current, level = [], len(heading[1])
        elif current is not None:
            current.append(line)
    if current is not None:
        blocks.append("\n".join(current).strip())
    return [b for b in blocks if b]


def refresh_editorial_queue(wiki: Path) -> int:
    """Append new discussions without dropping evidence or reopening resolutions."""
    destination = wiki / "_editorial" / "issues.json"
    issues = json.loads(destination.read_text(encoding="utf-8")) if destination.exists() else []
    if not isinstance(issues, list) or any(not isinstance(i, dict) or not i.get("id") for i in issues):
        raise ValueError("invalid editorial queue")
    seen = {i["id"] for i in issues}
    added = 0
    for path in wiki.rglob("*.md"):
        relative = path.relative_to(wiki)
        if any(part.startswith("_") for part in relative.parts) or path.name in {"AGENTS.md", "log.md"}:
            continue
        if not path.is_file() or not path.resolve().is_relative_to(wiki.resolve()):
            continue
        slug = relative.with_suffix("").as_posix()
        for block in discussion_sections(path.read_text(encoding="utf-8")):
            for chunk in re.split(r"(?m)(?=^\d+\.\s)", block):
                if not chunk.strip():
                    continue
                issue_id = hashlib.sha256((slug + chunk).encode()).hexdigest()[:16]
                if issue_id in seen:
                    continue
                issues.append({"id": issue_id, "page": slug, "original_text": chunk.strip(),
                               "status": "review", "resolution": None,
                               "created_at": datetime.now(timezone.utc).isoformat()})
                seen.add(issue_id)
                added += 1
    if added:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(issues, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return added
