"""Переписывание ссылок на VK-посты в ответах на ссылки нашей вики.

Ответы LLM цитируют посты как [текст](https://vk.com/...?w=wall-<group>_<id>).
Если этот пост процитирован в какой-то статье Летописи (storage/wiki/*.md),
читателю полезнее ссылка на статью: [текст](/wiki/<slug>).
Посты без статьи в вики остаются ссылками на VK.
Только стандартная библиотека — модуль едет и на slim-ВМ.
"""

import re
from pathlib import Path

from backend.wiki.loop import WIKI_DIR

WALL_RE = re.compile(r"wall-(\d+)_(\d+)")
_LINK_OR_URL_RE = re.compile(
    r"\[([^\]]*)\]\((https?://[^)\s]+)\)"  # [label](url)
    r"|(https?://[^\s<>\"')\]]+)"  # голый URL
)
_TAIL_PUNCT_RE = re.compile(r"[.,!?;:]+$")

_cache: dict[str, object] = {}


def build_wall_index(wiki_dir: Path | None = None) -> dict[str, list[str]]:
    """wall-<group>_<id> -> отсортированные слаги статей, где он упомянут."""
    root = Path(wiki_dir) if wiki_dir is not None else WIKI_DIR
    index: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        slug = path.relative_to(root).with_suffix("").as_posix()
        for m in WALL_RE.finditer(text):
            index.setdefault(f"wall-{m.group(1)}_{m.group(2)}", set()).add(slug)
    return {k: sorted(v) for k, v in index.items()}


def _wall_index(wiki_dir: Path | None = None) -> dict[str, list[str]]:
    """Ленивый индекс с инвалидацией по mtime (вики правится редко)."""
    root = Path(wiki_dir) if wiki_dir is not None else WIKI_DIR
    newest = 0.0
    try:
        for path in root.rglob("*.md"):
            try:
                newest = max(newest, path.stat().st_mtime)
            except OSError:
                continue
    except OSError:
        return {}
    key = str(root)
    hit = _cache.get(key)
    if isinstance(hit, tuple) and hit[0] == newest:
        return hit[1]
    index = build_wall_index(root)
    _cache[key] = (newest, index)
    return index


def wiki_url_for_post(url: str, wiki_dir: Path | None = None) -> str | None:
    """/wiki/<slug> для VK-ссылки на пост, если пост процитирован в Летописи."""
    m = WALL_RE.search(url)
    if not m:
        return None
    slugs = _wall_index(wiki_dir).get(f"wall-{m.group(1)}_{m.group(2)}")
    return f"/wiki/{slugs[0]}" if slugs else None


def rewrite_answer_links(answer: str, wiki_dir: Path | None = None) -> str:
    """[x](vk-пост) и голые vk-URL -> [x](/wiki/slug), где mapping известен."""
    if not answer or ("vk.com" not in answer and "wall-" not in answer):
        return answer

    def swap(url: str) -> str | None:
        return wiki_url_for_post(url, wiki_dir)

    def fix(m: re.Match) -> str:
        label, link_url, bare = m.group(1), m.group(2), m.group(3)
        if link_url is not None:
            return f"[{label}]({swap(link_url) or link_url})"
        tail = _TAIL_PUNCT_RE.search(bare or "")
        suffix = tail.group(0) if tail else ""
        core = bare[: -len(suffix)] if suffix else bare
        return f"{swap(core) or core}{suffix}"

    return _LINK_OR_URL_RE.sub(fix, answer)
