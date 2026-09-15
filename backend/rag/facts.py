"""Одна точка правды для фактов графа (Фаза 3 плана упрощения пайплайна).

Фикс найденного бага: role_title/даты терялись при форматировании, потому что
_fmt_facts() читал сырые dict'ы с разнобоем ключей (relation vs role_title,
links vs sources). Теперь оба потребителя — шаблоны (renderers.py) и
LLM-промпт (answer_generator._fmt_facts) — берут Fact, не сырой dict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from backend.common.canon import normalize_id


@dataclass
class Fact:
    """Строка графа в канонической форме."""

    person: str = "?"
    subject: str | None = None  # субъект факта (напр. поддерживаемая сторона)
    role_title: str | None = None
    event_date: str | None = None
    observed_at: str | None = None
    source_post_url: str | None = None
    # Сопроводительные поля (статус, тип связи, описание, объект, ссылки).
    status: str | None = None
    relation: str | None = None
    role_status: str | None = None
    description: str | None = None
    date: str | None = None  # legacy-дата ребра (v3: event_date/observed_at)
    org: str | None = None
    label: str | None = None
    links: list = field(default_factory=list)
    sources: list = field(default_factory=list)


_ROLE_STOP = frozenset(
    {"штаб", "штаба", "со", "кгэу", "тесла", "рсо", "отряд", "отряда",
     "центр", "центра", "направление", "направления", "проектный"}
)


def role_rank(role_title: str | None) -> int:
    """Ранг должности для сортировки и кресел (без имён, только слова).

    0 командир, 1 комиссар, 2 мастер, 3 пресса, 4 остальные.
    """
    t = normalize_id(role_title or "")
    if "командир" in t:
        return 0
    if "комиссар" in t:
        return 1
    if "мастер" in t:
        return 2
    if "пресс" in t:
        return 3
    return 4


def norm_role(role_title: str | None) -> str:
    """Должность без привязки к организации — ключ кресла."""
    toks = re.sub(r"[«»\"'()]", " ", normalize_id(role_title or "")).split()
    return " ".join(w for w in toks if w not in _ROLE_STOP and len(w) > 1)


def _fact_sort_date(f: Fact) -> str:
    return (f.event_date or f.observed_at or f.date or "")[:10]


def supersede_roles(facts: list[Fact]) -> list[Fact]:
    """Одно кресло — один действующий. Только даты и должности, имён нет.

    Группы-кресла: ранг 0/1 (командир, комиссар) — одно место: ключ (rank,),
    поэтому «Руководитель (командир)» и «Командир» — одно кресло.
    Остальные — по normalized должности (два мастера уживаются).
    Побеждает max дата; проигравшие (старше или без даты при датированном
    победителе) помечаются former. Без дат у всех — никого не гасим.
    Уже бывшие в победе не участвуют. Возвращает новые объекты.
    """
    groups: dict[tuple, list[int]] = {}
    for i, f in enumerate(facts):
        rank = role_rank(f.role_title or f.relation)
        key = ("seat", rank) if rank in (0, 1) else ("title", norm_role(f.role_title or f.relation))
        groups.setdefault(key, []).append(i)
    out = list(facts)
    for idxs in groups.values():
        contenders = [i for i in idxs if out[i].role_status != "former"]
        if len(contenders) < 2:
            continue
        dated = [(_fact_sort_date(out[i]), i) for i in contenders]
        if not any(d for d, _ in dated):
            continue  # дат нет ни у кого — честно показываем всех
        best = max(d for d, _ in dated)
        for d, i in dated:
            if d < best or (not d and best):
                out[i] = replace(out[i], role_status="former")
    return out


_ORG_KEYS = ("org", "object", "target", "award", "partner", "location", "project")
_LABEL_KEYS = ("event", "unit", "award", "location", "project", "id")


def rows_to_facts(rows: list[dict]) -> list[Fact]:
    """Сырые строки Cypher -> список Fact. Неизвестные ключи игнорируются."""
    facts = []
    for r in rows or []:
        if isinstance(r, Fact):
            facts.append(r)
            continue
        r = r or {}
        org = next((r.get(k) for k in _ORG_KEYS if r.get(k)), None)
        label = next((r.get(k) for k in _LABEL_KEYS if r.get(k)), None)
        facts.append(
            Fact(
                person=r.get("person") or "?",
                subject=r.get("subject"),
                role_title=r.get("role_title"),
                event_date=r.get("event_date"),
                observed_at=r.get("observed_at"),
                source_post_url=r.get("source_post_url"),
                status=r.get("status"),
                relation=r.get("relation"),
                role_status=r.get("role_status"),
                description=r.get("description"),
                date=r.get("date"),
                org=org,
                label=label,
                links=list(r.get("links") or []),
                sources=list(r.get("sources") or []),
            )
        )
    return facts
