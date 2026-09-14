"""Интент-схемы v2 (Фаза 1 плана упрощения пайплайна).

Вместо одной анкеты на 10 веток (PLANNER_SCHEMA с призрачным entity_type,
который то null, то "Role" без причины) — 10 маленьких pydantic-моделей,
каждая только с реально нужными полями. Модель-классификатор выбирает
ОДНУ схему за один вызов (см. backend/rag/query_planner.py).

Таблицы INTENT_TO_MODE / INTENT_TO_KIND заменяют часть логики роутера
обычным Python: режим и вид ответа детерминированы интентом.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field


class UnitsQuery(BaseModel):
    """Вопрос о списке отрядов/подразделений штаба или организации."""

    org_filter: str
    limit: int = 20


class CommandersQuery(BaseModel):
    """Вопрос о командирах/комиссарах/руководителях/составе штаба или отряда."""

    org_filter: str
    limit: int = 20


class MembersQuery(BaseModel):
    """Вопрос об участниках/бойцах отряда (не о командном составе)."""

    org_filter: str
    limit: int = 20


class WinnersQuery(BaseModel):
    """Вопрос о победителях, наградах, призовых местах."""

    org_filter: Optional[str] = None
    event_name: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    limit: int = 20


class PartnersQuery(BaseModel):
    """Вопрос о партнёрах/спонсорах/организациях, поддерживающих штаб или отряд."""

    org_filter: str
    limit: int = 20


class ProjectsQuery(BaseModel):
    """Вопрос о проектах/трудовых семестрах."""

    org_filter: Optional[str] = None
    limit: int = 20


class LocationsQuery(BaseModel):
    """Вопрос о местах проведения мероприятий."""

    org_filter: Optional[str] = None
    limit: int = 20


class EventsQuery(BaseModel):
    """Вопрос о мероприятиях/событиях, в т.ч. за период."""

    org_filter: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    limit: int = 20


class EntityDetailQuery(BaseModel):
    """Вопрос о конкретном человеке/сущности, НЕ о командном составе."""

    target_name: str


class GeneralQuery(BaseModel):
    """Всё остальное — открытые вопросы вне других категорий."""


INTENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "units": UnitsQuery,
    "commanders": CommandersQuery,
    "members": MembersQuery,
    "winners": WinnersQuery,
    "partners": PartnersQuery,
    "projects": ProjectsQuery,
    "locations": LocationsQuery,
    "events_in_period": EventsQuery,
    "entity_detail": EntityDetailQuery,
    "general": GeneralQuery,
}

INTENT_TO_MODE: dict[str, str | None] = {
    "units": "struct",
    "events_in_period": "struct",
    "commanders": "struct",
    "members": "struct",
    "winners": "struct",
    "projects": "struct",
    "locations": "struct",
    "partners": "struct",
    "entity_detail": "local",
    "general": None,  # решается classify_general_subtype()
}

INTENT_TO_KIND: dict[str, str] = {
    "units": "enumerable",
    "commanders": "enumerable",
    "members": "enumerable",
    "winners": "enumerable",
    "projects": "enumerable",
    "locations": "enumerable",
    "partners": "enumerable",
    "events_in_period": "enumerable",
    "entity_detail": "narrative",
    "general": "narrative",
}

_GLOBAL_MARKERS = ("в целом", "за всё время", "тенденции", "как менялось")


def classify_general_subtype(question: str) -> str:
    """Подтип general: global при маркерах обзора, иначе basic."""
    q = (question or "").lower()
    return "global" if any(m in q for m in _GLOBAL_MARKERS) else "basic"


@dataclass
class QueryPlan:
    """План v2: интент + режим + слоты + честная резолюция организации.

    org_norm_id — norm_id СУЩЕСТВУЮЩЕГО узла графа (проверен запросом),
    не копия org_filter.lower(). None = организация не распознана,
    запросы обязаны это учитывать, а не молча склеивать.
    """

    intent: str = "general"
    mode: str = "basic"
    kind: str = "narrative"
    org_filter: Optional[str] = None
    org_norm_id: Optional[str] = None
    target_name: Optional[str] = None
    event_name: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    relation: Optional[str] = None
    entity_type: Optional[str] = None
    limit: int = 20
    # Сколько LLM-вызовов ушло на классификацию+план (метрика Фазы 6).
    llm_calls: int = 0

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "mode": self.mode,
            "kind": self.kind,
            "org_filter": self.org_filter,
            "org_norm_id": self.org_norm_id,
            "target_name": self.target_name,
            "event_name": self.event_name,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "relation": self.relation,
            "entity_type": self.entity_type,
            "limit": self.limit,
        }
