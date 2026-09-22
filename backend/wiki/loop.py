"""Чистая Wiki: tools_loop поверх storage/wiki/*.md (GigaChat function calling).

Одна функция-вход: try_wiki_answer(question) -> dict | None.
None = в wiki нет данных (вызывающий код делает fallback в обычный RAG).
Модель ничего не исполняет: она лишь возвращает function_call,
исполняет _dispatch() локально, только чтением .md.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

WIKI_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "wiki"
MAX_TURNS = 5
READ_LIMIT = 6000

FUNCTIONS = [
    {
        "name": "wiki_search",
        "description": "Search compiled wiki pages about Tesla student squads. Call this first for any question. If snippet lacks dates or names, call wiki_read next. Never invent facts.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query, e.g. squad name and topic"},
                "top_k": {"type": "integer", "description": "How many snippets to return"},
            },
            "required": ["query"],
        },
        "few_shot_examples": [
            {"request": "Кто командовал СПО Юность в 2024?", "params": {"query": "Юность командир 2024", "top_k": 5}},
            {"request": "Где была целина Монолита?", "params": {"query": "Монолит целина", "top_k": 5}},
        ],
        "return_parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["success", "fail"]},
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "slug": {"type": "string"},
                            "section": {"type": "string"},
                            "snippet": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
    {
        "name": "wiki_read",
        "description": "Read full wiki page by slug with its outgoing links. Call after wiki_search when snippet lacks dates, names or sources.",
        "parameters": {
            "type": "object",
            "properties": {
                "slug": {"type": "string", "description": "Page slug, e.g. lso/spo_yunost"},
                "section": {
                    "type": "string",
                    "description": "Optional section heading to read instead of page head, e.g. Награды и достижения",
                },
            },
            "required": ["slug"],
        },
        "few_shot_examples": [
            {"request": "Подробнее про Юность", "params": {"slug": "lso/spo_yunost"}},
            {"request": "Награды Юности", "params": {"slug": "lso/spo_yunost", "section": "Награды и достижения"}},
        ],
        "return_parameters": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["success", "fail"]},
                "slug": {"type": "string"},
                "markdown": {"type": "string"},
                "links": {"type": "array", "items": {"type": "string"}},
                "sources": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
]

SYSTEM = (
    "Ты — Летописец Штаба СО КГЭУ «Тесла». Отвечай ТОЛЬКО по результатам функций. "
    "Различай дату публикации и дату события. Должность — только с годом. "
    "Каждый факт — сноска вида [текст](https://vk.com/...) из источников страниц. "
    "Не выводи разметку [[..]] наружу. Если данных нет — напиши ровно: В архивах нет данных."
)

_SLUG_RE = re.compile(r"^[a-z0-9_/]+$")
_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_MD_URL_RE = re.compile(r"\[[^\]]*\]\((https://[^)]+)\)")
_SKIP = {"AGENTS.md", "log.md"}
_NOINDEX = {"index.md", "timeline.md"}  # навигация: читается, но в поиске не участвует


def _pages() -> dict[str, Path]:
    out = {}
    for f in WIKI_DIR.rglob("*.md"):
        if f.name.startswith("_") or f.name in _SKIP:
            continue
        out[f.relative_to(WIKI_DIR).with_suffix("").as_posix()] = f
    return out


def _sections(text: str) -> list[tuple[str, str]]:
    parts = re.split(r"(?m)^## ", text)
    head, rest = parts[0], parts[1:]
    out = [("", head.strip())]
    for p in rest:
        title, _, body = p.partition("\n")
        out.append((title.strip(), body.strip()))
    return [(t, b) for t, b in out if b]


def wiki_search(query: str, top_k: int = 5) -> dict:
    # ponytail: naive substring rank over ~140 files; FTS5 if it measurably lags
    toks = [t.lower() for t in re.findall(r"[a-zа-яё0-9]+", query, re.I) if len(t) > 2]
    if not toks:
        return {"status": "fail", "items": []}
    # ponytail: наивный стемминг (обрезка 2 букв) вместо pymorphy; морфология — апгрейд при промахах
    stems = [t[:-2] if len(t) > 5 else t for t in toks]
    hits = []
    for slug, path in _pages().items():
        if path.name in _NOINDEX:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        low = text.lower()
        for title, body in _sections(text):
            hay = f"{title}\n{body}".lower()
            cover = sum(1 for t in toks if t in hay) + sum(1 for s in stems if s in hay)
            if not cover:
                continue
            score = 100 * cover + sum(hay.count(t) for t in toks) + sum(hay.count(s) for s in stems)
            hits.append((score, slug, title, body[:400]))
    hits.sort(reverse=True)
    return {
        "status": "success" if hits else "fail",
        "items": [{"slug": s, "section": t, "snippet": b} for _, s, t, b in hits[: max(1, top_k)]],
    }


def wiki_read(slug: str, section: str = "") -> dict:
    if not _SLUG_RE.match(slug or ""):
        return {"status": "fail", "error": "bad slug"}
    path = (WIKI_DIR / f"{slug}.md").resolve()
    if WIKI_DIR not in path.parents or not path.is_file():
        return {"status": "fail", "error": "not found"}
    text = path.read_text(encoding="utf-8")
    if section:
        want = section.strip().lower()
        for title, body in _sections(text):
            if want in title.lower():
                text = f"## {title}\n{body}"
                break
    return {
        "status": "success",
        "slug": slug,
        "markdown": text[:READ_LIMIT],
        "links": sorted(set(_LINK_RE.findall(text))),
        "sources": sorted(set(_MD_URL_RE.findall(text)))[:20],
    }


def _dispatch(name: str, args: dict) -> dict:
    if name == "wiki_search":
        return wiki_search(str(args.get("query", "")), int(args.get("top_k", 5) or 5))
    if name == "wiki_read":
        return wiki_read(str(args.get("slug", "")), str(args.get("section", "")))
    return {"status": "fail", "error": "unknown function"}


def try_wiki_answer(question: str, client=None) -> dict | None:
    """Ответ из wiki через tools_loop; None — нет данных, вызывающий делает fallback."""
    import os

    if client is None:
        if os.environ.get("TESLA_WIKI_ENABLED", "1") != "1":
            return None  # тесты/стенды без GigaChat: сразу fallback
        from backend.utils.gigachat_client import GigaChatClient

        client = GigaChatClient()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]
    used: list[str] = []
    sources: list[dict] = []
    state_id = None
    for _ in range(MAX_TURNS):
        try:
            resp = client.chat_with_functions(messages, FUNCTIONS)
        except Exception:
            return None
        msg = resp.get("message") or {}
        if msg.get("functions_state_id"):
            state_id = msg["functions_state_id"]
        fc = msg.get("function_call") or {}
        if resp.get("finish_reason") == "function_call" and fc.get("name"):
            args = fc.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            result = _dispatch(fc["name"], args if isinstance(args, dict) else {})
            if fc["name"] == "wiki_read" and result.get("status") == "success":
                if result["slug"] not in used:
                    used.append(result["slug"])
                for u in result.get("sources") or []:
                    s = {"title": result["slug"], "url": u}
                    if s not in sources:
                        sources.append(s)
            assistant = {"role": "assistant", "content": "", "function_call": {"name": fc["name"], "arguments": args}}
            if state_id:
                assistant["functions_state_id"] = state_id
            messages += [assistant, {"role": "function", "name": fc["name"], "content": json.dumps(result, ensure_ascii=False)}]
            continue
        answer = (msg.get("content") or "").strip()
        return {"answer": answer, "pages": used, "sources": sources[:10]} if answer else None
    try:  # последний шанс: прямой ответ без функций
        resp = client.chat_with_functions(messages, FUNCTIONS, function_call="none")
        answer = ((resp.get("message") or {}).get("content") or "").strip()
    except Exception:
        return None
    return {"answer": answer, "pages": used, "sources": sources[:10]} if answer else None
