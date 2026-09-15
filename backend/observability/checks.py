"""Слой 1: детерминированные проверки каждого ответа (Фаза 2).

Бесплатно, без LLM. Институционализация находок диалога:
- даты — выдуманная дата Астафьева;
- иерархия — домысел «ПрогрессLAB — часть Штаба»;
- «пусто, но уверенно» — баги с партнёрами и Хазиевым.

Это триаж-инструмент, не жёсткий гейт: ложные срабатывания ожидаемы,
флаги разбираются в Слое 3 / вручную.
"""

from __future__ import annotations

import re

_DATE_RE = re.compile(r"\b((?:19|20)\d{2}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}\.(?:19|20)\d{2})\b")
_HIERARCHY_PHRASES = (
    "входит в состав",
    "является частью",
    "являются частью",
    "подчинён",
    "подчинен",
    "подчиняется",
)
_SILENCE_PHRASES = ("нет данных", "в архивах нет", "не зафиксирована",
                    "не зафиксирован", "точная дата", "не приводится")


def known_dates(graph_facts: list[dict]) -> set[str]:
    """Все даты, за которые граф готов поручиться."""
    known: set[str] = set()

    def _add(v):
        if v:
            known.add(str(v)[:10])

    for f in graph_facts or []:
        _add((f.get("event_date") or "") if isinstance(f, dict) else None)
        if not isinstance(f, dict):
            continue
        _add(f.get("observed_at"))
        _add(f.get("date"))
        for link in f.get("links") or []:
            if isinstance(link, dict):
                _add(link.get("event_date"))
                _add(link.get("observed_at"))
                _add(link.get("date"))
    return {d for d in known if d}


def check_groundedness_of_dates(answer: str, graph_facts: list[dict]) -> bool:
    """Каждая дата YYYY-MM-DD в ответе есть среди дат фактов."""
    dates = {m.group(1)[:10] for m in _DATE_RE.finditer(answer or "")}
    if not dates:
        return True
    return dates <= known_dates(graph_facts)


def check_hierarchy_claim(answer: str, graph_facts: list[dict]) -> bool:
    """Утверждение об иерархии требует PART_OF-факта.

    Возвращает True, если всё чисто (утверждения нет или факт есть).
    """
    text = (answer or "").lower()
    if not any(p in text for p in _HIERARCHY_PHRASES):
        return True
    for f in graph_facts or []:
        if not isinstance(f, dict):
            continue
        rels = {f.get("relation")}
        for link in f.get("links") or []:
            if isinstance(link, dict):
                rels.add(link.get("rel"))
        if "PART_OF" in rels:
            return True
    return False


def check_empty_but_confident(graph_facts: list[dict], n_posts: int,
                              answer: str) -> bool:
    """Пусто в источниках, но ответ уверенный (без оговорки тишины)."""
    if graph_facts or n_posts:
        return True
    text = (answer or "").lower()
    return any(p in text for p in _SILENCE_PHRASES)


def run_layer1(answer: str, graph_facts: list[dict],
               n_posts: int = 0) -> dict:
    """Все три проверки одним вызовом. Ключи = колонки traces."""
    return {
        "groundedness_ok": check_groundedness_of_dates(answer, graph_facts),
        "hierarchy_claim_flag": not check_hierarchy_claim(answer, graph_facts),
        "empty_but_confident_flag": not check_empty_but_confident(
            graph_facts, n_posts, answer),
    }
