"""VK-группы: чтение group_links.txt + статусы спарсенного."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from backend.config import BASE_DIR

LINKS_FILE = BASE_DIR / "storage" / "posts" / "group_links.txt"
POSTS_DIR = BASE_DIR / "storage" / "posts"
GROUPS_DIR = BASE_DIR / "storage" / "groups"


def domain_of(url: str) -> str:
    try:
        path = urlparse(url.strip()).path.strip("/")
        return path.split("/")[0]
    except Exception:
        return ""


def read_links() -> list[dict]:
    """Строки group_links.txt: {url, domain, enabled} (# = выключена)."""
    if not LINKS_FILE.exists():
        return []
    out = []
    for line in LINKS_FILE.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        enabled = not s.startswith("#")
        url = s.lstrip("#").strip()
        if not url:
            continue
        out.append({"url": url, "domain": domain_of(url), "enabled": enabled})
    return out


def append_link(url: str) -> dict:
    url = url.strip()
    if not url.startswith("http"):
        raise ValueError("нужен http(s) URL группы")
    existing = {g["url"] for g in read_links()}
    if url in existing:
        raise ValueError("такая ссылка уже есть")
    LINKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LINKS_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")
    return {"url": url, "domain": domain_of(url), "enabled": True}


def _count_jsonl(path: Path) -> int:
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def group_statuses() -> list[dict]:
    """Группы + спарсенное: посты (jsonl) и мета (groups_*.json)."""
    out = []
    for g in read_links():
        domain = g["domain"]
        posts_file = POSTS_DIR / f"posts_{domain}.jsonl"
        meta_file = GROUPS_DIR / f"groups_{domain}.json"
        meta_name = ""
        if meta_file.exists():
            try:
                meta_name = str(json.loads(meta_file.read_text(encoding="utf-8")).get("name", ""))
            except Exception:
                pass
        out.append(
            {
                **g,
                "posts_count": _count_jsonl(posts_file) if posts_file.exists() else 0,
                "posts_mtime": posts_file.stat().st_mtime if posts_file.exists() else 0,
                "meta_name": meta_name,
            }
        )
    return out
