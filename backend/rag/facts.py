"""Одна точка правды для фактов графа (Фаза 3 плана упрощения пайплайна).

Фикс найденного бага: role_title/даты терялись при форматировании, потому что
_fmt_facts() читал сырые dict'ы с разнобоем ключей (relation vs role_title,
links vs sources). Теперь оба потребителя — шаблоны (renderers.py) и
LLM-промпт (answer_generator._fmt_facts) — берут Fact, не сырой dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Fact:
    """Строка графа в канонической форме."""

    person: str = "?"
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
                person=r.get("person") or r.get("subject") or "?",
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
