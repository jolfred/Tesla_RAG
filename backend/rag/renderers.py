"""Детерминированные шаблоны ответов для enumerable-интентов (Фаза 4).

Чистый Python, 0 LLM-вызовов, unit-тестируются точным сравнением строк.
Контракт: пустой список фактов -> None (сигнал на hybrid vector-fallback,
НЕ «нет данных» — тишину печатает только searcher, когда пуст и fallback).

Формулировки про ПрогрессLAB зависят от флага PROGRESSLAB_IS_SUBORDINATE
(Фаза 0): при False структура, связанная с ПрогрессLAB, никогда не
называется «частью Штаба» — только тем, что реально есть в факте.
"""

from __future__ import annotations

from backend.common.canon import normalize_id
from backend.config import PROGRESSLAB_IS_SUBORDINATE
from backend.rag.facts import Fact, rows_to_facts


def _subordinate_note(name: str) -> str:
    """Оговорка для ПрогрессLAB при недоказанной подчинённости."""
    if "прогрессlab" in normalize_id(name or "") and not PROGRESSLAB_IS_SUBORDINATE:
        return " (связанная структура, подчинение не подтверждено)"
    return ""


def _role_line(f: Fact) -> str:
    role = f.role_title or "должность не указана"
    line = f"• {f.person} — {role}"
    if f.event_date:
        line += f" (с {f.event_date[:10]})"
    elif f.observed_at:
        line += f" (упоминание от {f.observed_at[:10]})"
    if f.role_status == "former":
        line += " [экс]"
    line += _subordinate_note(f.org or "")
    return line


def render_commanders(facts: list[Fact], org_name: str) -> str | None:
    if not facts:
        return None
    lines = [_role_line(f) for f in facts]
    return f"Командный состав «{org_name}»:\n" + "\n".join(lines)


def render_units(facts: list[Fact], org_name: str) -> str | None:
    if not facts:
        return None
    names = [f.label or f.person for f in facts]
    lines = [f"• {n}{_subordinate_note(n)}" for n in names]
    return f"Отряды «{org_name}»:\n" + "\n".join(lines)


def render_members(facts: list[Fact], org_name: str) -> str | None:
    if not facts:
        return None
    lines = []
    for f in facts:
        line = f"• {f.person}"
        if f.role_title:
            line += f" — {f.role_title}"
        lines.append(line)
    return f"Участники «{org_name}»:\n" + "\n".join(lines)


def render_winners(facts: list[Fact], org_name: str) -> str | None:
    if not facts:
        return None
    lines = []
    for f in facts:
        award = f.org or f.label or "награда не указана"
        line = f"• {f.person} — {award}"
        if (f.relation or "") == "PARTICIPATED_IN":
            line += " (участие, не победа)"
        if f.event_date:
            line += f" ({f.event_date[:10]})"
        lines.append(line)
    return f"Награды «{org_name}»:\n" + "\n".join(lines)


def render_partners(facts: list[Fact], org_name: str) -> str | None:
    if not facts:
        return None
    lines = []
    for f in facts:
        partner = f.org or (f.person if f.person != "?" else None) or f.label or "?"
        line = f"• {partner}"
        if f.subject and f.subject != partner:
            line += f" (поддерживает {f.subject})"
        line += _subordinate_note(partner)
        lines.append(line)
    return f"Партнёры «{org_name}»:\n" + "\n".join(lines)


def _render_labeled(header: str, facts: list[Fact], org_name: str) -> str | None:
    if not facts:
        return None
    lines = [f"• {f.label or f.person}" for f in facts]
    return f"{header} «{org_name}»:\n" + "\n".join(lines)


def render_projects(facts: list[Fact], org_name: str) -> str | None:
    return _render_labeled("Проекты", facts, org_name)


def render_locations(facts: list[Fact], org_name: str) -> str | None:
    return _render_labeled("Локации", facts, org_name)


def render_events(facts: list[Fact], org_name: str) -> str | None:
    if not facts:
        return None
    lines = []
    for f in facts:
        line = f"• {f.label or f.person}"
        if f.event_date:
            line += f" ({f.event_date[:10]})"
        lines.append(line)
    return f"Мероприятия «{org_name}»:\n" + "\n".join(lines)


def render_person_roles(facts: list[Fact], person_name: str) -> str | None:
    """Фаза 5: детерминированный блок ролей персоны для entity_detail."""
    if not facts:
        return None
    name = next((f.person for f in facts if f.person != "?"), person_name)
    lines = []
    for f in facts:
        role = f.role_title or f.relation or "роль не указана"
        org = f.org or f.label or "?"
        line = f"• {role} — {org}"
        if f.event_date:
            line += f" (с {f.event_date[:10]})"
        elif f.observed_at:
            line += f" (упоминание от {f.observed_at[:10]})"
        if f.role_status == "former":
            line += " [экс]"
        lines.append(line)
    return f"«{name}»:\n" + "\n".join(lines)


RENDERERS = {
    "units": render_units,
    "commanders": render_commanders,
    "members": render_members,
    "winners": render_winners,
    "projects": render_projects,
    "locations": render_locations,
    "partners": render_partners,
    "events_in_period": render_events,
}


def render(intent: str, rows: list[dict], org_name: str) -> str | None:
    """Точка входа диспетчера: сырые строки -> шаблонный текст или None."""
    fn = RENDERERS.get(intent)
    if fn is None:
        return None
    return fn(rows_to_facts(rows), org_name)
