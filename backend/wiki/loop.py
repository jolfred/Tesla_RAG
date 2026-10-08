"""Чистая Wiki: tools_loop поверх storage/wiki/*.md (GigaChat function calling).

Одна функция-вход: try_wiki_answer(question) -> dict | None.
None = в wiki нет подтверждённого ответа. Legacy fallback отсутствует.
Модель ничего не исполняет: она лишь возвращает function_call,
исполняет _dispatch() локально, только чтением .md.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from backend.wiki.editorial import public_markdown

WIKI_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "wiki"
MAX_TURNS = 5
READ_LIMIT = 6000
SILENCE = "В архивах нет данных."


class WikiUnavailable(RuntimeError):
    """Wiki provider or canonical instructions are unavailable."""

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
                "offset": {"type": "integer", "description": "Continue reading from next_offset returned by a truncated fragment"},
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
_TITLE_RE = re.compile(r"(?m)^# (.+?)\s*$")
_KIND_RE = re.compile(r"(?m)^kind:\s*(\S+)\s*$")
_REDIRECT_RE = re.compile(r"(?m)^redirect_to:\s*([a-z0-9_/]+)\s*$")
_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
_MD_URL_RE = re.compile(r"\[[^\]]*\]\(((?:https://|/api/v1/wiki/source\?)[^)]+)\)")
_SKIP = {"AGENTS.md", "log.md"}
_NOINDEX = {"index.md", "timeline.md"}  # навигация: читается, но в поиске не участвует
_STATUS_RE = re.compile(r"(?m)^status:\s*stub\s*$")
_STOP = {"кто", "что", "как", "какой", "какая", "какие", "когда", "где", "был", "была", "были", "это", "про", "для", "год", "году", "ссо", "спо", "сэо", "осд", "смо", "соп", "ссерв"}


def _terms(text: str) -> list[str]:
    words = re.findall(r"[a-zа-я0-9]+", text.lower().replace("ё", "е"))
    result = []
    for word in words:
        if len(word) < 3 or word in _STOP:
            continue
        if word.startswith("команд"):
            word = "команд"
        elif word.startswith("комисс"):
            word = "комисс"
        elif len(word) > 5:
            word = re.sub(r"(?:ами|ями|ого|ему|ому|ах|ях|ой|ей|ов|ев|ы|и|а|я|у|ю|е)$", "", word)
        if word not in result:
            result.append(word)
    return result


def page_meta(slug: str, path: Path) -> dict:
    """Заголовок (первый `# ...`) и kind (frontmatter, иначе верхний каталог)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"slug": slug, "title": slug, "kind": slug.split("/")[0] if "/" in slug else "wiki"}
    m = _TITLE_RE.search(text)
    k = _KIND_RE.search(text)
    title = (m.group(1).strip() if m else slug)[:120]
    kind = k.group(1).strip() if k else (slug.split("/")[0] if "/" in slug else "wiki")
    meta = {"slug": slug, "title": title, "kind": kind}
    redirect = _REDIRECT_RE.search(text)
    if redirect:
        meta["redirect_to"] = redirect[1]
    return meta


def wiki_graph() -> dict:
    """Узлы — страницы, рёбра — [[ссылки]] на существующие страницы."""
    pages = _pages()
    metadata = {s: page_meta(s, p) for s, p in sorted(pages.items())}
    nodes = [meta for meta in metadata.values() if "redirect_to" not in meta]
    seen: set[tuple[str, str]] = set()
    edges = []
    for slug, path in pages.items():
        if "redirect_to" in metadata[slug]:
            continue
        try:
            text = public_markdown(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        for target in set(_LINK_RE.findall(text)):
            target = metadata.get(target, {}).get("redirect_to", target)
            if target in pages and target != slug and (slug, target) not in seen:
                seen.add((slug, target))
                edges.append({"source": slug, "target": target})
    return {"nodes": nodes, "edges": edges}


def _pages() -> dict[str, Path]:
    out = {}
    for f in WIKI_DIR.rglob("*.md"):
        if not f.is_file() or not f.resolve().is_relative_to(WIKI_DIR.resolve()):
            continue
        if any(p.startswith("_") for p in f.relative_to(WIKI_DIR).parts) or f.name in _SKIP:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        if _STATUS_RE.search(text):
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
    toks = _terms(query)
    if not toks:
        return {"status": "fail", "items": []}
    hits = []
    for slug, path in _pages().items():
        if path.name in _NOINDEX:
            continue
        try:
            text = public_markdown(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if _REDIRECT_RE.search(text):
            continue
        page_title = page_meta(slug, path)["title"].lower().replace("ё", "е")
        identity = sum(1 for t in toks if not t.isdigit() and t in page_title)
        for title, body in _sections(text):
            for offset in range(0, max(1, len(body)), 1000):
                chunk = body[offset:offset + 1400]
                hay = f"{title}\n{chunk}".lower().replace("ё", "е")
                matched = [t for t in toks if t in hay]
                if not matched:
                    continue
                score = identity * 500 + len(matched) * 30
                score += sum(80 for t in toks if t in title.lower().replace("ё", "е"))
                score += sum(50 for t in matched if t.isdigit())
                positions = [chunk.lower().replace("ё", "е").find(t) for t in matched]
                start = max(0, min((p for p in positions if p >= 0), default=0) - 120)
                hits.append((score, slug, title, chunk[start:start + 600], offset + start))
    hits.sort(reverse=True)
    selected = []
    seen = set()
    for _, slug, title, snippet, offset in hits:
        if (slug, title) in seen:
            continue
        seen.add((slug, title))
        selected.append({"slug": slug, "section": title, "snippet": snippet, "offset": offset})
        if len(selected) >= max(1, min(top_k, 20)):
            break
    return {
        "status": "success" if hits else "fail",
        "items": selected,
    }


def wiki_read(slug: str, section: str = "", offset: int = 0, *, full: bool = False) -> dict:
    if not _SLUG_RE.match(slug or ""):
        return {"status": "fail", "error": "bad slug"}
    path = (WIKI_DIR / f"{slug}.md").resolve()
    if WIKI_DIR.resolve() not in path.parents or slug not in _pages():
        return {"status": "fail", "error": "not found"}
    text = public_markdown(path.read_text(encoding="utf-8"))
    redirect = _REDIRECT_RE.search(text)
    if redirect:
        target = redirect[1]
        pages = _pages()
        if target == slug or target not in pages:
            return {"status": "fail", "error": "invalid redirect"}
        target_text = public_markdown(pages[target].read_text(encoding="utf-8"))
        if _REDIRECT_RE.search(target_text):
            return {"status": "fail", "error": "redirect chain"}
        slug, text = target, target_text
    if section:
        want = section.strip().lower()
        for title, body in _sections(text):
            if want in title.lower():
                text = f"## {title}\n{body}"
                break
        else:
            return {"status": "fail", "error": "section not found"}
    if offset < 0 or offset >= max(1, len(text)):
        return {"status": "fail", "error": "bad offset"}
    fragment = text if full else text[offset:offset + READ_LIMIT]
    sources = sorted(set(_MD_URL_RE.findall(fragment)))
    from backend.wiki.sources import source_details
    return {
        "status": "success",
        "slug": slug,
        "markdown": fragment,
        "links": sorted(set(_LINK_RE.findall(fragment))),
        "sources": sources,
        "source_details": source_details(sources, WIKI_DIR),
        "truncated": not full and offset + len(fragment) < len(text),
        "next_offset": offset + len(fragment) if not full and offset + len(fragment) < len(text) else None,
        "total_chars": len(text),
    }


def _dispatch(name: str, args: dict) -> dict:
    if name == "wiki_search":
        return wiki_search(str(args.get("query", "")), int(args.get("top_k", 5) or 5))
    if name == "wiki_read":
        return wiki_read(str(args.get("slug", "")), str(args.get("section", "")), int(args.get("offset", 0) or 0))
    return {"status": "fail", "error": "unknown function"}


def try_wiki_answer(question: str, client=None, *, raise_on_error: bool = False) -> dict | None:
    """Answer using bounded Wiki reads; failures never initiate another retrieval path."""
    import os

    if client is None:
        if os.environ.get("TESLA_WIKI_ENABLED", "1") != "1":
            return None  # Wiki отключена для этого стенда.
        from backend.utils.gigachat_client import GigaChatClient

        client = GigaChatClient()
    from backend.wiki.prompts import query_prompt
    try:
        system = query_prompt()
    except OSError as exc:
        if raise_on_error:
            raise WikiUnavailable("Не удалось загрузить правила Летописи.") from exc
        return None
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    used: list[str] = []
    sources: list[dict] = []
    calls: list[dict] = []

    def finish(answer: str) -> dict | None:
        if not answer:
            return None
        if answer == SILENCE:
            return {"answer": answer, "pages": used, "sources": [], "calls": calls}
        cited = set(_MD_URL_RE.findall(answer))
        known = {s["url"].rstrip(".,;"): s for s in sources}
        if not used or not cited or any(u.rstrip(".,;") not in known for u in cited):
            return None
        if "[[" in answer or any(
                not _MD_URL_RE.search(block) for block in re.split(r"\n\s*\n", answer)
                if block.strip() and not all(re.match(r"^\s*#{1,6}\s", line) for line in block.splitlines() if line.strip())):
            return None
        def readable_citation(match):
            label, url = match.groups()
            if re.fullmatch(r"(?:источник\s+)?(?:wall-?\d+_\d+|archive:.+|group:.+)", label, re.IGNORECASE):
                detail = known.get(url.rstrip(".,;"), {})
                label = str(detail.get("title") or "Публикация")[:120].replace("[", "(").replace("]", ")")
            return f"[{label}]({url})"
        answer = re.sub(r"\[([^\]]+)\]\(((?:https?://|/api/v1/wiki/source\?)[^)]+)\)", readable_citation, answer)
        return {"answer": answer, "pages": used, "sources": [known[u.rstrip(".,;")] for u in sorted(cited)], "calls": calls}
    state_id = None

    def checked_response(response: dict) -> dict:
        if not isinstance(response, dict) or not isinstance(response.get("message"), dict):
            raise ValueError("invalid provider response")
        message = response["message"]
        if message.get("content") is not None and not isinstance(message["content"], str):
            raise ValueError("invalid provider content")
        if message.get("function_call") is not None and not isinstance(message["function_call"], dict):
            raise ValueError("invalid provider function call")
        return response

    for _ in range(MAX_TURNS):
        try:
            resp = checked_response(client.chat_with_functions(messages, FUNCTIONS))
        except Exception as exc:
            if raise_on_error:
                raise WikiUnavailable("Летопись временно недоступна. Попробуйте позже.") from exc
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
            if not isinstance(args, dict):
                args = {}
            try:
                if fc["name"] == "wiki_read" and len(used) >= 5 and args.get("slug") not in used:
                    result = {"status": "fail", "error": "page budget exhausted; use pages already read"}
                else:
                    result = _dispatch(fc["name"], args if isinstance(args, dict) else {})
            except (TypeError, ValueError):
                result = {"status": "fail", "error": "invalid function arguments"}
            calls.append({"name": fc["name"], "arguments": args, "result": result})
            if fc["name"] == "wiki_read" and result.get("status") == "success":
                if result["slug"] not in used:
                    used.append(result["slug"])
                for s in result.get("source_details") or []:
                    if s not in sources:
                        sources.append(s)
            assistant = {"role": "assistant", "content": "", "function_call": {"name": fc["name"], "arguments": args}}
            if state_id:
                assistant["functions_state_id"] = state_id
            messages += [assistant, {"role": "function", "name": fc["name"], "content": json.dumps(result, ensure_ascii=False)}]
            continue
        answer = (msg.get("content") or "").strip()
        result = finish(answer)
        if result is not None or not used or not sources:
            return result
        messages += [{"role":"assistant", "content":answer}, {"role":"user", "content":
            "Revise using only the evidence already read. Return a short Russian answer. Every non-heading paragraph must contain its own Markdown primary-source citation from the tool results. Do not output internal [[Wiki links]], file paths, unsupported claims, or uncited summaries. Use descriptive citation labels. If evidence is absent, return exactly: В архивах нет данных."}]
    try:  # последний шанс: прямой ответ без функций
        resp = checked_response(client.chat_with_functions(messages, FUNCTIONS, function_call="none"))
        answer = ((resp.get("message") or {}).get("content") or "").strip()
    except Exception as exc:
        if raise_on_error:
            raise WikiUnavailable("Летопись временно недоступна. Попробуйте позже.") from exc
        return None
    return finish(answer)
