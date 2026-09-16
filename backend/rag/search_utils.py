"""Чистые хелперы read-пути: окна вызовов, детект дублей прозы, годы, даты."""

import re

from backend.rag.facts import rows_to_facts

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_BULLET_RE = re.compile(r"^\s*(?:•|[-*]|\d+[.)])\s+")
_CONGRATS_RE = re.compile(r"дн[её]м рождения|поздравля|happy birthday", re.IGNORECASE)
_DATE_HINT_RE = re.compile(r"(?:19|20)\d{2}|\d{1,2}[.\-]\d{1,2}[.\-]\d{2,4}")


def _fmt_call_window(exchanges: list[dict], extra: str = "") -> str:
    """Одно окно вызова: полные тексты запроса и ответа (fidelity).

    Ретраи складываются стопкой с заголовками попыток. Ничего не режется.
    """
    parts = []
    for i, ex in enumerate(exchanges):
        if len(exchanges) > 1:
            parts.append(f"--- попытка {i + 1} ---")
        for m in ex.get("messages") or []:
            parts.append(f"=== {str(m.get('role', '')).upper()} ===\n{m.get('content', '')}")
        parts.append(f"=== ОТВЕТ ===\n{ex.get('response', '')}")
    if extra:
        parts.append(extra)
    return "\n\n".join(parts) if parts else "— вызовов не было —"


def narrative_repeats_list(graph_facts: list[dict], answer: str,
                           structured: str | None) -> bool:
    """Проза дублирует блок (п.1 отзыва): прозу выкинуть.

    Два триггера: (а) список — ≥2 буллетов с именами, покрывающих
    ≥ половины имён; (б) пересказ без добавленной стоимости — от 3 имён,
    большинство упомянуто и ни одной даты (проза ничего не добавила).
    Очерк об одном человеке (1–2 имени) никогда не давим: упоминание
    имени там естественно. Абзац с датами — не дубль, пропускаем.
    """
    prose = (answer[len(structured):]
             if structured and answer.startswith(structured) else answer)
    if not prose.strip():
        return False
    names = set()
    for f in rows_to_facts(graph_facts or []):
        for v in (f.person, f.subject, f.label):
            if v and v != "?" and len(v) > 2:
                names.add(v.lower())
    if not names:
        return False
    lowered = prose.lower()
    mentioned = {n for n in names if n in lowered}
    if len(mentioned) * 2 < len(names):
        return False
    named_bullets = sum(
        1 for ln in prose.splitlines()
        if _BULLET_RE.match(ln) and any(n in ln.lower() for n in names)
    )
    if named_bullets >= 2:
        return True
    # Пересказ без дат: от 3 имён, большинство упомянуто, информации
    # не добавлено (ровно половина — пограничный случай, пропускаем).
    return (len(names) >= 3 and len(mentioned) * 2 > len(names)
            and _DATE_HINT_RE.search(prose) is None)


def question_year(question: str) -> str | None:
    """Единственный год из вопроса (п.8) — для фильтра на всех путях."""
    years = sorted(set(_YEAR_RE.findall(question or "")))
    return years[0] if len(years) == 1 else None


def _fact_date(f: dict) -> str:
    """Дата факта для сортировки (п.10): сначала event_date, при отсутствии —
    observed_at/date. Свежее важнее, но дата события бьёт дату упоминания."""
    events, mentions = [], []

    def _add(d, bucket):
        if d:
            bucket.append((d or "")[:10])

    _add(f.get("event_date"), events)
    _add(f.get("observed_at"), mentions)
    _add(f.get("date"), mentions)
    for link in f.get("links") or []:
        if isinstance(link, dict):
            _add(link.get("event_date"), events)
            _add(link.get("observed_at"), mentions)
            _add(link.get("date"), mentions)
    pool = events or mentions
    return max(pool) if pool else ""


def _filter_posts_by_period(
    posts: list[dict], start: str | None, end: str | None
) -> list[dict]:
    """Оставить посты внутри [start, end] (ISO). Карточки group:// — всегда."""
    if not start and not end:
        return posts
    kept = []
    for p in posts:
        url = p.get("post_url") or ""
        if url.startswith("group://"):
            kept.append(p)
            continue
        pub = (p.get("published_at") or "")[:10]
        if not pub:
            kept.append(p)
            continue
        if start and pub < start[:10]:
            continue
        if end and pub > end[:10]:
            continue
        kept.append(p)
    return kept
