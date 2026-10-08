"""Readable primary-source bibliography; no LLM or database service required."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {"posts_kgeu_official.jsonl", "posts_spoyunost.jsonl"}
_cache: dict = {}


def source_key(url: str) -> str:
    match = re.search(r"wall-?\d+_\d+", url)
    return match.group() if match else url.rstrip(".,;:!?")


def build_source_index(posts_dir: Path | None = None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in sorted((posts_dir or ROOT / "storage" / "posts").glob("posts_*.jsonl")):
        if path.name in EXCLUDED:
            continue
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                try:
                    post = json.loads(line)
                except (ValueError, TypeError):
                    continue
                url = post.get("post_url") or ""
                if not url:
                    continue
                text = post.get("text_clean") or post.get("text") or ""
                text = re.sub(r"\[https?://[^|]+\|([^\]]+)\]", r"\1", text)
                text = re.sub(r"https?://\S+|#\w+", "", text)
                headline = re.split(r"[\n.!?]", text.strip(), maxsplit=1)[0].strip()
                out[source_key(url)] = {
                    "url": url, "title": headline[:180] or "Публикация отряда",
                    "group_name": post.get("group_name") or post.get("group_domain") or "",
                    "published_at": post.get("published_at") or "",
                }
    groups_dir = (posts_dir.parent / "groups") if posts_dir else ROOT / "storage" / "groups"
    for path in sorted(groups_dir.glob("groups_*.json")):
        if path.name in {"groups_kgeu_official.json", "groups_spoyunost.json"}:
            continue
        try:
            group = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(group, dict):
            continue
        domain = group.get("domain")
        if not domain or domain in {"kgeu_official", "spoyunost"}:
            continue
        url = f"https://vk.com/{domain}"
        out[url] = {"url": url, "title": "Описание сообщества", "group_name": group.get("name") or domain, "published_at": ""}
    from backend.wiki.archive import read_records
    wiki_dir = posts_dir.parent / "wiki" if posts_dir else ROOT / "storage" / "wiki"
    for record in read_records(wiki_dir).values():
        out[source_key(record["url"])] = {k: record.get(k, "") for k in ("url", "title", "group_name", "published_at")}
    return out


def source_index(wiki_dir: Path) -> dict[str, dict]:
    bibliography = wiki_dir / "_sources.json"
    paths = [bibliography] if bibliography.exists() else sorted((ROOT / "storage" / "posts").glob("posts_*.jsonl")) + sorted((ROOT / "storage" / "groups").glob("groups_*.json"))
    registry = wiki_dir / "_source_records.json"
    if registry.exists():
        paths.append(registry)
    signature = tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    key = str(wiki_dir.resolve())
    if _cache.get(key, (None,))[0] != signature:
        if bibliography.exists():
            try:
                index = json.loads(bibliography.read_text(encoding="utf-8"))
                if not isinstance(index, dict):
                    index = {}
            except (ValueError, OSError):
                index = {}
        else:
            index = build_source_index()
        from backend.wiki.archive import read_records
        for record in read_records(wiki_dir).values():
            index[source_key(record["url"])] = {k: record.get(k, "") for k in ("url", "title", "group_name", "published_at")}
        _cache[key] = (signature, index)
    return _cache[key][1]


def source_details(urls: list[str], wiki_dir: Path) -> list[dict]:
    index = source_index(wiki_dir)
    return [{**index.get(source_key(url), {"title": "Публикация", "group_name": "", "published_at": ""}), "url": url} for url in urls]
