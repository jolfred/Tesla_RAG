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
from backend.rag.facts import Fact, role_rank, rows_to_facts


def _subordinate_note(name: str) -> str:
    """Оговорка для ПрогрессLAB при недоказанной подчинённости."""
    if "прогрессlab" in normalize_id(name or "") and not PROGRESSLAB_IS_SUBORDINATE:
        return " (связанная структура, подчинение не подтверждено)"
    return ""


# Иерархия комсостава (пользовательское правило): командир -> комиссар ->
# мастер -> пресса -> остальные. Первый — всегда командир.
# Ранг — facts.role_rank (там же используется для кресел supersede).


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
    ordered = sorted(facts, key=lambda f: (role_rank(f.role_title), f.person))
    lines = [_role_line(f) for f in ordered]
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
    """Партнёры без 20-кратного суффикса: субъект — один раз в заголовок."""
    if not facts:
        return None
    subjects = sorted({f.subject or "" for f in facts} - {""})
    header = f"Партнёры «{org_name}»"
    if len(subjects) == 1:
        header += f" (поддерживают {subjects[0]})"
    header += ":"
    lines = [header]
    for f in facts:
        partner = f.org or (f.person if f.person != "?" else None) or f.label or "?"
        line = f"• {partner}"
        if len(subjects) != 1 and f.subject:
            line += f" (поддерживает {f.subject})"
        line += _subordinate_note(partner)
        lines.append(line)
    return "\n".join(lines)


def _render_labeled(header: str, facts: list[Fact], org_name: str) -> str | None:
    if not facts:
        return None
    lines = [f"• {f.label or f.person}" for f in facts]
    return f"{header} «{org_name}»:\n" + "\n".join(lines)


def render_projects(facts: list[Fact], org_name: str) -> str | None:
    return _render_labeled("Проекты", facts, org_name)


def render_locations(facts: list[Fact], org_name: str) -> str | None:
    return _render_labeled("Локации", facts, org_name)


def _event_date(f: Fact) -> str | None:
    if f.event_date:
        return f.event_date[:10]
    for link in f.links or []:
        for key in ("event_date", "observed_at", "date"):
            if link.get(key):
                return str(link[key])[:10]
    return None


def _event_urls(f: Fact, cap: int = 2) -> list[str]:
    urls: list[str] = []
    if f.source_post_url:
        urls.append(f.source_post_url)
    for link in f.links or []:
        u = link.get("source_post_url")
        if u and u not in urls:
            urls.append(u)
    return urls[:cap]


def render_events(facts: list[Fact], org_name: str | None) -> str | None:
    """Мероприятия с датой и ссылкой; дубли схлопываются.

    Дубли: нормализованное имя содержится в другом («Школа Кандидатов
    И Бойцов» vs «… «Погружение»») — оставляем более полное имя,
    ссылки дублей добираем.
    """
    if not facts:
        return None
    kept: list[list] = []  # [key, label, fact]
    for f in facts:
        label = f.label or f.person
        key = normalize_id(label)
        if not key:
            continue
        for entry in kept:
            if key == entry[0] or key in entry[0] or entry[0] in key:
                if len(label) > len(entry[1]):
                    entry[1] = label
                kept_fact = entry[2]
                if f.event_date and not kept_fact.event_date:
                    kept_fact.event_date = f.event_date
                if f.observed_at and not kept_fact.observed_at:
                    kept_fact.observed_at = f.observed_at
                have = set(_event_urls(kept_fact))
                for u in _event_urls(f):
                    if u not in have:
                        kept_fact.links.append({"source_post_url": u})
                        have.add(u)
                break
        else:
            kept.append([key, label, f])
    header = f"Мероприятия «{org_name}»:" if org_name and org_name != "архив" else "Мероприятия:"
    lines = [header]
    for _, label, f in kept:
        line = f"• {label}"
        date = _event_date(f)
        if date:
            line += f" — {date}"
        for u in _event_urls(f):
            line += f" · {u}"
        lines.append(line)
    return "\n".join(lines)


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


def fmt_facts(graph_facts: list[dict]) -> str:
    """Факты для LLM-контекста (одна точка правды — из Fact, не из dict).

    Переехало из AnswerGenerator: форматирование — дело рендереров.
    role_title — первичен: «Комиссар», а не голый тип связи COMMANDED.
    """
    facts = rows_to_facts(graph_facts)
    if not facts:
        return "Нет данных графа."
    lines = []
    for f in facts[:60]:
        subj = f.person if f.person != "?" else (f.subject or f.label or "?")
        rel = f.role_title or f.relation or ""
        obj = f.org or ""
        event_date = (f.event_date or "")[:10]
        observed_at = (f.observed_at or "")[:10]
        date = f.date
        job = subj
        if rel:
            job += f" ({rel}"
            if obj:
                job += f": {obj}"
            job += ")"
        elif obj:
            job += f" — {obj}"
        # Честная семантика дат (пункт 6/10): «с <дата>» только при
        # подтверждённом событии, иначе — «упоминание в посте от».
        if event_date:
            job += f" | с {event_date}"
        elif observed_at:
            job += f" (упоминание в посте от {observed_at})"
        elif date:
            job += f" | дата: {date}"
        line = job
        if f.status:
            line += f" [{f.status}]"
        if f.role_status == "former":
            line += " [экс/бывший]"
        if f.description:
            line += f" — {f.description[:120]}"
        if not (rel or obj or date) and f.links:
            dates = sorted({l.get("date") for l in f.links if l.get("date")})
            if dates:
                line += f" | даты: {', '.join(d[:10] for d in dates[:5])}"
        urls = []
        if f.source_post_url:
            urls.append(f.source_post_url)
        for l in f.links or []:
            u = l.get("source_post_url")
            if u and u not in urls:
                urls.append(u)
        for s in f.sources or []:
            if s and s not in urls:
                urls.append(s)
        if urls:
            line += f" | источники: {', '.join(urls[:3])}"
        lines.append("- " + line)
    return "\n".join(lines)


def fmt_edges(links: list) -> str:
    if not links:
        return ""
    parts = []
    for l in links:
        rel = l.get("rel") or l.get("rtype") or ""
        tgt = l.get("target") or l.get("target_id") or ""
        event_date = (l.get("event_date") or "")[:10]
        observed_at = (l.get("observed_at") or "")[:10]
        date = l.get("date")
        url = l.get("source_post_url")
        part = f"{rel}{' → ' + tgt if tgt else ''}"
        if event_date:
            part += f" (с {event_date})"
        elif observed_at:
            part += f" (упом. {observed_at})"
        elif date:
            part += f" ({str(date)[:10]})"
        if l.get("role_status") == "former":
            part += " [экс]"
        if url:
            part += f" [{url}]"
        parts.append(part)
    return "; ".join(parts)


def post_stamp(p: dict) -> str:
    # Только дата без времени: сырые ISO-метки засоряют контекст и ответы.
    return (p.get("published_at") or "")[:10]
